#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDG to PDF Converter (超星 PDG 格式转 PDF 工具)
基于 https://github.com/bj5/pdg2pdf_open 修改与增强

功能特性:
  1. 支持 ZIP 压缩包（含加密 ZIP 自动匹配密码/手动输入）、文件夹或单个 PDG 文件直接输入
  2. 完整支持超星 00H / 02H 加密与私有 CCITT 2D 游程格式解码，100% 清晰还原无花屏黑条
  3. 标准化无损封装：解码后转为国际标准 ITU-T CCITT Group 4 TIFF，经 img2pdf 极速无损封装进 PDF
  4. 按超星标准阅读序排序：
     cov(0) -> bok(1) -> leg(2) -> fow(3) -> !(4) -> toc/dir(5) -> 数字正文(6) -> att(8) -> bac/cov002(9)
  5. 默认按正文页宽无损对齐封面与插页显示尺寸（解决低分辨率封面显得过小的问题）
  6. 自动提取并生成图书元数据与多级目录大纲书签
  7. 自动修复极小占位页（如 1x1 像素）及超大尺寸页面，避免触发 PDF 规范尺寸限制
  8. 支持批量目录扫描转换 (-b)、递归扫描 (-r)、断点续转 (-s) 与多线程并发加速 (-w)
  9. 内置超大常用电子书解压密码库（近 700 条密码自动匹配尝试）

使用方法:
  python pdg2pdf.py <input_paths...> [-o output_path] [-b] [-r] [-s] [-w workers] [--dpi 200]
"""

import os
import sys
import glob

# 自动定位并优先加载同目录下的 .venv / venv 虚拟环境依赖库
# 避免用户在未执行 'source .venv/bin/activate' 时因缺失 wasmtime/img2pdf/pikepdf 报错
_script_dir = os.path.dirname(os.path.abspath(__file__))
for _venv_name in ('.venv', 'venv'):
    _site_pattern = os.path.join(_script_dir, _venv_name, 'lib', 'python*', 'site-packages')
    for _site in glob.glob(_site_pattern):
        if os.path.isdir(_site) and _site not in sys.path:
            sys.path.insert(0, _site)

import argparse
import base64
import getpass
import io
import math
import re
import threading
import time
import zipfile
import zlib
from typing import List, Tuple, Dict, Any, Optional, Union

from PIL import Image
import img2pdf
import pikepdf
from tqdm import tqdm

try:
    import wasmtime
    HAS_WASMTIME = True
except ImportError:
    HAS_WASMTIME = False

try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

# 支持的图书页面文件格式（PDG 格式及常见导出的标准图像格式）
VALID_PAGE_EXTS = ('.pdg', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')

# 256 字节位反转查表（C 层一次性完成反色）
_INV_TABLE = bytes(range(255, -1, -1))

_ZIP_PWD_ERRORS = (RuntimeError, zipfile.BadZipFile, zlib.error, EOFError)
if HAS_PYZIPPER:
    _ZIP_PWD_ERRORS = _ZIP_PWD_ERRORS + (pyzipper.BadZipFile,)

# 常见超星 PDG / 电子书 ZIP 密码库
COMMON_ZIP_PASSWORDS = (
    '12345678',
    'hsz123456',
    '6622Ee',
    '662Ee',
    '52gv',
    '28zrs',
    'julian',
    'www.eshuyuan.com',
    'wcpfxk&*^TDwcpfxk',
    '风云07E319B496B3467&%CFE14AF3',
    'wcpfxk&*^TDwcpfxk@8686',
    'huihuirenjianrenaihuajianhuakai',
    '多读好书',
    '多多读书',
    '以书为伴',
    '孔方兄沧海横流',
    '奥哈哈aaa123',
    '以书为友',
    '以书会友',
    '52GV',
    '53gv',
    '5gv',
    '52gz',
    'fesga',
    'Wsz123',
    '1234560',
    '75753',
    '8888888',
    'yumi007BFY',
    'xuexileifenghaobanyang',
    '毛论',
    'deepsea',
    'Yuntai',
    'yutai',
    '555gv',
    '3333Ee',
    '123',
    '1234',
    '666666',
    '75487',
    '2345',
    '1235',
    'qwer',
    '123456',
    'efgzzz',
    'eg123',
    '123321',
    'gdfgdfgdfghjjj4444',
    'ytuytiuyiouy3',
    'erte645567uytuytu',
    'fesga123',
    'Ferge',
    'www.eshuyuan.net',
    'ddd111',
    'zdfsf',
    'sdfsdfdsf',
    'rwerewrtgfddg',
    'fgdsretgfdbfd',
    'dfgryytiurtt',
    'jggfj',
    'rytr',
    'hrty',
    'rtyiuuyo',
    'hjkkjl',
    'jkl112',
    'uyyut4556',
    'rtyuio',
    '毛浙东',
    '天天学习',
    'fdsffdf',
    'sdfsdfsdf',
    'tyrtuoyt5',
    'jhjh6',
    'ghjhgjghj555',
    'oiuytrfdf55588869',
    'niuniu154',
    '45678999trtrtrtrtr',
    'fffffff',
    'nnnnnnn',
    'mmmmmm',
    'rwrertyyuyretet6556',
    'dfgdfgdfgdfg26565',
    'www5555',
    'Yutien',
    'yutien',
    'ccwn84237hdwkhd',
    'zlpxqck',
    '13579',
    '935mpirsy634',
    'zgwenhuazsdb',
    'xuelejinxian52134guoxuehuiyankuaile',
    'xjb516518',
    'badcc2',
    'lcga110@163.com',
    '天涯的心',
    'WJDHhxsh',
    'DYFYDYR',
    'GCQMS5678jizhou',
    '郭德纲救了张纪中和王宝强',
    '大范甘迪让更多人',
    '认真你就输 了',
    'YLSSJYYSYZQ',
    'qm20150404lxpz',
    'SWDLQwangxiaobo',
    'esy',
    'gxxehjh',
    'HTYSfhcqZXMZFbymgjjmf',
    '3453453453453434',
    '87654321',
    'ssdd2013',
    'fsJDSS3',
    'akichina2015',
    'HNLLRsfnsSGH',
    'HM2729jyh293XSJ',
    'sddfrtry56hfgswr4tgdvdsda',
    '23545345346345334',
    '2342342343234',
    '刚毅.狮子心',
    'dfgdfgdfhghjhkioluiopio',
    '457871345654',
    '353467tertdrgdfg',
    'gfddgdfghjkhjk6269',
    '老程书库',
    '后掌书房',
    '天天读书哭',
    'dfsdfdsfds55555',
    'ddd555666',
    'ddd111222',
    'eee333',
    '4444444eeeee',
    'ttt888',
    'rgth',
    'yhjuiklo',
    'p;lo',
    'xz123',
    '热爱书园',
    'hahaha',
    'foxaaron',
    'julianyoung',
    'ZWZGQJEYHTEH5789658326987jkdcdfgtazZGFLHZZZT',
    'c867f7d5c9b44760519b3a4ffabfd84b',
    'c8f4e136b7a328867a82149021cea9d0',
    'cd38f6275fffd00f41726311bb6b7a5f',
    'f00b1c5b49df6e9b95064b1518706381',
    'ff378a3167a35335e320dc7d90652334',
    'F90315379E77760EE4FAB1916DAE84D6',
    'F33002B42D45F551CFC208BBC932F286',
    '64916565d10cba76a97ce9db9f40d957',
    'd247888e0048096c6d1bc9eb129b3e6f',
    'd6247f4c4f2caf2bb691c85109200f99',
    'd9289a11454320a54d1d973bf8f4315f',
    '02293048c80af2325b101fe51edca57a',
    '171077796a81b47d3c42c52dbac1d5dc',
    '295280df3927be407120d45456637c35',
    '3016f9cc97613122ee1ef67bdfb0fb4a',
    '34e1cfa99379ae9e819492a926b8576a',
    '3a84334169ad06ea2d4406b3811306a5',
    '4ff3b559833bff133c044d1aa4961c1a',
    '6baac99bab72711a1242b7f33c14db42',
    '7c08d5969530c4750057e6f1e7524498',
    '833a82081923d1e4c48d5bed9837572c',
    '872c8e99c6e449487e6421ee29fd5a77',
    '887818d87132250b88d660eb8032518d',
    '99320f53aeac97ed54f5fabdbc63d716',
    'ec80b73075fb05982c89869424e9be5f',
    'a80818325ce01bc94c938a8f6c2429bf',
    'aadbf3be35b87659771eb6687dc93622',
    'ab67ccce04735f95aedf81874019cfab',
    'afac2a419ff07dfe7ed9dd7d6ae632fa',
    'A7E544982C9611AA27B5332B36DD1F08',
    'A991A2C8747F0D19A6D2367BEE0E19B2',
    'be62ad5c350c400858de9c7bf281ccab',
    '54654756856754654634',
    'E书园',
    '你需要的一切&纪念品',
    '内部资料请勿传播',
    'www.foundpdf.com',
    'www.ddddffffff',
    'sdfg###',
    'eeeeee#########',
    'wszcdgf123',
    'serdfhg1233',
    'eresdf666',
    'eeefffff',
    '345efsf',
    'wwwwwwddddd',
    'rrrrrrrrrrrrr',
    'zxxzx',
    'dfdfe13',
    'wert456',
    'asdfg2335',
    'sdfghj555',
    'xsh20132052@%',
    'eshuyuan.net',
    '[www.eshuyuan.net]',
    'eshuyuan.com',
    '%',
    'BSQY2007',
    'zia08812',
    '起风了fdsg@$',
    '147258369',
    '12345',
    '杰尔马66',
    '国学数典',
    '继￥#@续￥*发&*几#@&本',
    'dushubaoku',
    'www.eshuyuan.net_by',
    'dsds0831',
    'efg111',
    'efg',
    '解压密码：www.cxacg.vip',
    '大O饿O龙',
    'mucynav.com',
    '千秋漫雪',
    'atx123',
    '马忽悠',
    'long',
    '123450',
    '扶她奶茶www.futanaicha.club',
    '1205794039',
    '1105',
    '36.5℃',
    'www.cxacg.vip',
    'mayuyu123',
    '四散的尘埃',
    'acg和谐区',
    'acgzone.us',
    'http://acgzone.us/',
    'acgzone.tk',
    '琉璃神社',
    'hacg.me',
    '节操粉碎机',
    'i-ab.com',
    'www.tianshi2.com',
    'galgame：ACG游戏开发部',
    'galgame:mobi.acgfuture.com',
    '光影交错的时空',
    '扶她奶茶',
    '樱花树下实现',
    'yhsxsx',
    '没有节操的灵梦',
    '毛玉mouyu',
    'e46852s',
    '傲娇零：',
    'aojiao.org',
    '黙示',
    '天照大御神',
    '猫与好天气',
    'lifaner.com',
    '456black',
    'moe',
    '动漫本子吧',
    '里番儿',
    'lsmj',
    '良时美景',
    '674434350',
    'psp.duowan.com',
    '御宅同萌',
    'tangtang',
    '9999',
    '999',
    '士凛密码',
    '渺',
    '通宵狂魔技术宅',
    'benzi',
    'Q10',
    'malow005',
    'www.idanmu.com',
    '名字就是',
    '827283516',
    'ce',
    '绅士党',
    'hentai.',
    'tianshi2',
    '妮妙',
    '发条奶茶',
    '七曜苏醒',
    'yaoying',
    'gg',
    'air',
    '爱有缘有份',
    'softpoint',
    'YES',
    '我没有节操',
    '拉杰尔的图书馆',
    '20131225',
    'RoC_1112@eyny',
    'tianshi2.com',
    '180998244',
    'ntr',
    'CR48',
    'inori',
    'BQ510',
    '120505478',
    '社会主义歼星炮',
    '技术宅',
    'YL714',
    '八幡hachiman',
    'yomishibai',
    'galacg.me',
    'ky8787',
    'www.diaosiqingnian',
    '终点',
    'say花火',
    'acgmoon',
    '804423314',
    '北+7355608 12345678',
    '北+7355608',
    'channelc.yeah.net',
    'comicz.yeah.net',
    'kcomic.yeah.net',
    'www.comicer.com',
    'www.dqcx.net',
    'xcomic.yeah.net#6622ee',
    '#6622ee ',
    '*******************************************',
    '007',
    '00XX',
    '11',
    '119',
    '12306@',
    '12345678 ',
    '124',
    '1cga1100163.com',
    '1z2x1z',
    '20131225 ',
    '2013324',
    '2013324 ',
    '23110046',
    '23110046 ',
    '2djgame',
    '3016f9cc97613122eelef67bdfbefb4a',
    '520',
    '523046178',
    '528z',
    '52SB',
    '52gv ',
    '54103',
    '54240847',
    '54240847 ',
    '5518109',
    '5518109 ',
    '5518109 @CNGBA',
    '5518109@CNGBA',
    '5hgal',
    '654321',
    '6622Ee ',
    '674434350 psp.duowan.com',
    '674434350psp.duowan.com',
    '691d43689ebecbafd474328f3d82a706',
    '75ag',
    '827283516 ',
    '861944438',
    '9999或999',
    '@、提琴寄',
    '@、提琴寄 ',
    'ACG游戏开发部',
    'AsmodeusSama',
    'CNGBA',
    'Creeper',
    'DS真萝莉，傲娇救世界',
    'DespairTCK#Music',
    'F社资源组',
    'F社资源部',
    'GAL汉化组',
    'GG',
    'GMHAndDeepmoon',
    'Genesis',
    'HCG',
    'HENTAI',
    'Heart2',
    'MMD',
    'OOXX',
    'Oneeee',
    'PADIO',
    'PIBC损失惨重',
    'To Heart2',
    'ToHeart2',
    'WODHhxsh',
    'ZODGAME',
    '[链接登录后可见]',
    'aadbf33be35b87659771eb6687dc93622',
    'abacab',
    'acgzone.us ',
    'ammyyk',
    'anhgwwe',
    'aojiao',
    'ap',
    'arnocrash',
    'baidu',
    'bbs.acg183.com',
    'bbs.hlmbbs.com',
    'bin936272080',
    'by 23110046 ',
    'by23110046',
    'cCwn84237hdwkhd',
    'ccwwss',
    'cd38f6275fffdeef41726311bb6b7a5f',
    'darknight',
    'darkzwei@sstm',
    'suifeng',
    'fenghuang',
    'e_e‘死灵',
    'ec8b73075fb05982c89869424e9be5f',
    'efgl11',
    'ehentai',
    'eshuvuan.net',
    'eshuyan.com',
    'exhentai.org',
    'fuliba.net',
    'galgame',
    'galgame:mobi.',
    'gmgard.us',
    'gmgard.us ',
    'guishen',
    'gwh',
    'gxxehih',
    'h5gal',
    'hacg.me ',
    'hang.cg',
    'hentai. ',
    'hentai_萝莉控',
    'hentaihentai123',
    'http://acgzone.us/ ',
    'http://www.5w8.net-rtqy',
    'http://www.5w8.net-rtqy ',
    'http://www.acgft.us',
    'http://www.acgft.us ',
    'http://www.bwd108.com',
    'http://www.bwd108.com ',
    'http://www.cciup.com',
    'http://www.cciup.com ',
    'http://www.ccwzz.cc',
    'http://www.ccwzz.cc ',
    'http://www.hacg.me',
    'http://www.hacg.me ',
    'http://www.kcjc.net/',
    'http://www.kcjc.net/ ',
    'http://www.tianshi2.com',
    'http://www.tianshi2.com ',
    'jenocake',
    'jj',
    'joung4bld',
    'jukun',
    'karasu',
    'kcjc',
    'kofzec',
    'lionsky',
    'lzc20070101',
    'lzc20070101 ',
    'maple是个大好人',
    'mazochina.com',
    'me.searchbook.cn',
    'mh123456',
    'mobi.',
    'moe ',
    'momo123',
    'neteshuyuancom',
    'oxgood',
    'oxgood.com',
    'pikapi',
    'ps',
    'qaxxxx',
    'qm201504041xpz',
    'reaction李',
    'rp2j',
    'sdfhb&*^TD',
    'shana520@苍雪的世界',
    'shi十年nian',
    'sstm',
    'szgwsw',
    'tangtang ',
    'tiansh',
    'tianshi',
    'tianshi100',
    'tianshi1000',
    'tongueless',
    'tongueless@zodgame',
    'tr4869',
    'uuycw',
    'w w w . 5 w 8 . n e t - r t q y',
    'w101126',
    'w3655627',
    'w3655627 ',
    'wafter',
    'wcpfxk&*ATDwcpfxk',
    'wcpfxk&*^TD',
    'wcpfxk&*^TDwcpfxk@8686 ',
    'wcpfxk&TDwcpfxk',
    'wcpfxk&TDwcpfxk@8686',
    'wo88662244',
    'wo88662244 ',
    'ws123',
    'wwl588',
    'www.5w8.net-rtqy',
    'xcomic.yeah.net',
    'xib516518',
    'xsh201320520',
    'xzmsn',
    'yaoyicheng0322',
    'yukoyuko@tsdm.net@taikoyc@gn00',
    'yukoyuko@tsdm.net@taikoyc@gn00图包',
    'zfz930',
    'zhaozeren33',
    'zxcvbnm1876',
    'zzvv',
    '⑨',
    '「5518109 @CNGBA」',
    '「5518109@CNGBA」',
    '「CNGBA」',
    '七曜苏醒 ',
    '七条天空',
    '不给',
    '举报狗家破人亡',
    '么么哒',
    '乐章谱奏的夕阳',
    '什么的',
    '什么的...',
    '傲娇零：aojiao.org',
    '傲娇零：aojiao.org ',
    '傲娇黑猫控',
    '光影交错',
    '光影交错的时空 ',
    '光影娘',
    '全都没有啦',
    '关怀同癖好的人',
    '冰糖',
    '冰糖@2013324',
    '冰糖@2013324 ',
    '别再问我了',
    '别来问我',
    '动漫本子',
    '十神巨胖',
    '华丽的泡泡龙',
    '又被吧主吃了',
    '和以前不一样了',
    '和谐区公用密码',
    '咲夜我爱死你了',
    '哥特loli控',
    '四散的尘埃@来一斤莲酱',
    '四散的尘埃@来一斤莲酱。',
    '土豆开门',
    '在厕所自慰的男人',
    '堕落流行',
    '士凛密码 名字就是',
    '士凛密码名字就是',
    '复制了个寂寞',
    '夏目茗葑',
    '多喝开水身体好@开水saltytata',
    '夜之苍穹',
    '天兆大甲鱼',
    '奥哈哈aa123',
    '奶昔宝宝',
    '如此萝莉怎能不啪?',
    '如此萝莉怎能不啪？',
    '妖光之玥',
    '宅之圣地',
    '审判之锤维塔',
    '密码显示错误',
    '小白兔东仪白',
    '尘埃飘散尽',
    '就不设置了',
    '居然是合集版',
    '居然是合集版！',
    '山本天下',
    '幸福天七是个基佬',
    '幻之瞳',
    '开水saltytata',
    '心游之域',
    '忧郁的弟弟',
    '快要坏掉的翠星石',
    '总是被吧主吃掉',
    '我不告诉你',
    '我又逃课了',
    '我就是不说',
    '我就是神既是我',
    '我是傲娇控',
    '扶他奶茶',
    '扶她奶茶 ',
    '找本子必备',
    '捂脸联盟',
    '掌中萌虎',
    '掺水',
    '日月光影',
    '曲线绝版男',
    '月舞双天',
    '来一斤莲酱',
    '来一斤莲酱。',
    '果然节操什么的还是扔掉最好',
    '桂言叶',
    '桐人',
    '桐人＆审判之锤维塔',
    '樱祭天华',
    '橙橙好萌',
    '欢迎购买本店商品',
    '永远留在二次元',
    '沙耶の呗',
    '沙耶の呗@苍雪的世界',
    '没有了',
    '流觞·清影',
    '浮萍居主',
    '淫色明月',
    '漫酱final',
    '爱她干她',
    '爱有缘有份 ',
    '狂风明澜',
    '由依喵@9456123',
    '由依喵@9456123 ',
    '白羊我是大怪兽',
    '百世流离',
    '破晓之拓',
    '社会主义优越性的充分体现',
    '社会主义歼星炮 ',
    '社会主义歼星舰',
    '禁止转载,谢谢合作',
    '禁止转载，谢谢合作',
    '素我',
    '绅士会议',
    '绅士议会',
    '绝望的怮哭',
    '绝望的恸哭',
    '继￥#@续￥发&几#@&本',
    '继￥#续￥*发*几#本',
    '编辑公',
    '网盘特殊密码',
    '节操粉碎机 ',
    '苍雪论坛会员“沙耶の呗”上传',
    '苏橙橙uuu',
    '苹.果',
    '苹果',
    '菊火',
    '菊爆党操你妈',
    '虚空无限',
    '被吧主吃了',
    '西行妖樱',
    '言叶君',
    '认真你就输了',
    '诀影_流年',
    '起风了fdsg@',
    '足控绅士菌',
    '轮部_kisama',
    '迷雾之流',
    '造福全人类',
    '遍100',
    '邪恶的忧郁君',
    '阳光小志xx',
    '陪在女巫身边',
    '雪之本境',
    '风云e7e319496B3467cfe14af3',
    ' zy^^^***666888',
    '飘过武神',
    '飘过武神*****',
    '飘过武神54103',
    '食蜂操祈',
    '黑曜石',
    '6622E',
    '让我们一起追寻',
    'wsz2016',
    '48b8f79cbffb559c904299fe358e3fbb是是是',
    '起风了fdsg@..147258369',
    '新编禽病快速诊',
    'zy^^^***666888',
    'yjj',
    '1cga110@163.com',
    '111111',
    '123456789',
    'NOSPEAK',
    'nopdg',
    'c867f7d5c9b44768519b3a4ffabfd84b',
    'A991A2C8747F0D19A6D2367BEEOE19B2',
    'eshuvuan.net..[www.eshuyuan.net]..eshuyuan.com',
    '2cc608bb3e652275cd0c4fcd311ce5b',
    '0241eb2d6e6549135b99a8d16b70634f',
    '5c3941a67e6174d20b00ca0840e143ba',
    'da764c5f720a7a87968d8b4815aab371',
    'd5217551f36e70c227c762483850',
    '********************************************',
    '3.45345E+15',
    '2.35453E+16',
    '2.34234E+12',
    '4.57871E+11',
    '444444eeeee',
    '5.46548E+19',
    'wcpfxk&ATDwcpfxk',
    'wcpfxk&^TDwcpfxk',
    'wcpfxk&^TDwcpfxk@8686',
    '继￥#续￥发*几#本',
    '#6622ee',
    '48b8f79cbffb559c904299fe358e3fbb',
)

# 内嵌超星 00H/02H 专用高精度解码器 WASM 模块 (16KB)
PDG_DECODER_WASM_B64 = """
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AiAIQQJ0aiIAIAk2AgAgACAJNgIIIAAgCTYCBCACIARBAnRqIAk2AgBBfiEEIAhBfkYNAEEAIQQgCEEASA0AIAJC//////f/////ADcC+P8BIAJC//////f/////ADcC8P8BIBsgECAUbGohBiAUBEAgBkEAIBT8CwALIAhBAk8EQCAWIAJBgIAC/AoAACAIQQFrIRdBACEAA0ACQCAWIABBAnRqIggoAgAiByAIKAIEIgggGSAIIBlJGyIJTw0AQYB+IAlBB3F1IQhB/wEgB0EHcXYhCyAJQQN2IgkgB0EDdiIHRgRAIAYgB2oiByAHLQAAIAggC3FyOgAADAELIAYgB2oiESARLQAAIAtyOgAAIAhB/gFxBEAgBiAJaiILIAstAAAgCHI6AAALIAkgB2siCEECSQ0AIAhBAWsiCEUNACARQQFqQf8BIAj8CwALIABBAmoiACAXSA0ACwsCQCAYIA8gEGtPDQAgDkExSg0AIBAgGE0NACATQQJNBEAgDkEBaiEODAELAkACQCAGKAIADQBBACEAA0AgBiAAQQJ0aigCAA0BIBogAEEBaiIARw0ACwwBC0EAIQAgBiATQQJ0akEEayIIKAIADQECQANAIAggAEECdGsoAgBFBEBBASEHIBogAEEBaiIARw0BDAILC0EAIQcLIAcgDmohDgwBCyAOQQFqIQ4LIAIhACAQQQFqIhAgD0cNAQsLIBYQAQsgAxABIAwQASANEAELIAVBIGokACASEAFBe0F8IARBfkYbQQAgBBshDAsgFUEQaiQAIAwLBgAgABABCzcBAX8gAEEFdiAAQR9xQQBHakECdCEAAkAgAQRAIAGtIACtfkIgiKcNAQsgACABbBACIQILIAILQgACf0H/ASABQRBJDQAaQf8BIAAtAABByABHDQAaQf8BIAAtAAFByABHDQAaQX8gAC0ADyIAIABB/QFxGwtB/wFxCy0BAX8CQCABQRRJDQAgAC0AAEHIAEcNACAALQABQcgARw0AIAAvABIhAgsgAgsEACMACxAAIwAgAGtBcHEiACQAIAALBgAgACQACy0BAX8CQCABQRRJDQAgAC0AAEHIAEcNACAALQABQcgARw0AIAAvABAhAgsgAgsCAAsL8AkCAEGACAvgCQcABAACAAgABAADAAsABAAEAAwABAAFAA4ABAAGAA8ABAAHAAcABQAKAAgABQALABIABQCAABMABQAIABQABQAJABsABQBAAAMABgANAAcABgABAAgABgAMABcABgDAABgABgCABioABgAQACsABgARADQABgAOADUABgAPAAMABwAWAAQABwAXAAgABwAUAAwABwATABMABwAaABcABwAVABgABwAcACQABwAbACcABwASACgABwAYACsABwAZADcABwAAAQIACAAdAAMACAAeAAQACAAtAAUACAAuAAoACAAvAAsACAAwABIACAAhABMACAAiABQACAAjABUACAAkABYACAAlABcACAAmABoACAAfABsACAAgACQACAA1ACUACAA2ACgACAAnACkACAAoACoACAApACsACAAqACwACAArAC0ACAAsADIACAA9ADMACAA+ADQACAA/ADUACAAAADYACABAATcACACAAUoACAA7AEsACAA8AFIACAAxAFMACAAyAFQACAAzAFUACAA0AFgACAA3AFkACAA4AFoACAA5AFsACAA6AGQACADAAWUACAAAAmcACACAAmgACABAApgACQDABZkACQAABpoACQBABpsACQDABswACQDAAs0ACQAAA9IACQBAA9MACQCAA9QACQDAA9UACQAABNYACQBABNcACQCABNgACQDABNkACQAABdoACQBABdsACQCABQgACwAABwwACwBABw0ACwCABxIADADABxMADAAACBQADABACBUADACACBYADADACBcADAAACRwADABACR0ADACACR4ADADACR8ADAAACgIAAgADAAMAAgACAAIAAwABAAMAAwAEAAIABAAGAAMABAAFAAMABQAHAAQABgAJAAUABgAIAAQABwAKAAUABwALAAcABwAMAAQACAANAAcACAAOABgACQAPAAgACgASAA8ACgBAABcACgAQABgACgARADcACgAAAAgACwAABwwACwBABw0ACwCABxcACwAYABgACwAZACgACwAXADcACwAWAGcACwATAGgACwAUAGwACwAVABIADADABxMADAAACBQADABACBUADACACBYADADACBcADAAACRwADABACR0ADACACR4ADADACR8ADAAACiQADAA0ACcADAA3ACgADAA4ACsADAA7ACwADAA8ADMADABAATQADACAATUADADAATcADAA1ADgADAA2AFIADAAyAFMADAAzAFQADAAsAFUADAAtAFYADAAuAFcADAAvAFgADAA5AFkADAA6AFoADAA9AFsADAAAAWQADAAwAGUADAAxAGYADAA+AGcADAA/AGgADAAeAGkADAAfAGoADAAgAGsADAAhAGwADAAoAG0ADAApAMgADACAAMkADADAAMoADAAaAMsADAAbAMwADAAcAM0ADAAdANIADAAiANMADAAjANQADAAkANUADAAlANYADAAmANcADAAnANoADAAqANsADAArAEoADQCAAksADQDAAkwADQAAA00ADQBAA1IADQAABVMADQBABVQADQCABVUADQDABVoADQAABlsADQBABmQADQCABmUADQDABmwADQAAAm0ADQBAAnIADQCAA3MADQDAA3QADQAABHUADQBABHYADQCABHcADQDABABB4RELAosB
"""

_WASM_LOCK = threading.Lock()
_WASM_ENGINE = None
_WASM_MODULE = None


def get_wasm_module():
    """获取或初始化 WASM 解码模块（线程安全）"""
    global _WASM_ENGINE, _WASM_MODULE
    if not HAS_WASMTIME:
        raise RuntimeError("请安装 wasmtime 库以支持超星 PDG 解码: pip install wasmtime")

    with _WASM_LOCK:
        if _WASM_MODULE is None:
            _WASM_ENGINE = wasmtime.Engine()
            wasm_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdg-decoder.wasm')
            if os.path.exists(wasm_file):
                with open(wasm_file, 'rb') as f:
                    wasm_bytes = f.read()
            else:
                wasm_bytes = base64.b64decode(PDG_DECODER_WASM_B64.strip())
            _WASM_MODULE = wasmtime.Module(_WASM_ENGINE, wasm_bytes)

        return _WASM_ENGINE, _WASM_MODULE


class PdgDecoderSession:
    """PDG WASM 解码会话"""

    def __init__(self):
        engine, module = get_wasm_module()
        self.engine = engine
        self.store = wasmtime.Store(engine)
        self.memory = None

        def resize_heap(size):
            if self.memory:
                curr = self.memory.data_len(self.store)
                if size > curr:
                    pages = (size - curr + 65535) // 65536
                    self.memory.grow(self.store, pages)
            return 1

        resize_func = wasmtime.Func(
            self.store,
            wasmtime.FuncType([wasmtime.ValType.i32()], [wasmtime.ValType.i32()]),
            resize_heap
        )
        self.instance = wasmtime.Instance(self.store, module, [resize_func])
        exports = self.instance.exports(self.store)
        self.memory = exports['b']
        self.pdg_get_width = exports['d']
        self.pdg_get_height = exports['e']
        self.pdg_get_format = exports['f']
        self.pdg_alloc_bitmap = exports['g']
        self.malloc = exports['h']
        self.pdg_free = exports['i']
        self.free = exports['j']
        self.pdg_decode_file = exports['l']

    def decode_to_standard_tiff(self, raw_bytes: bytes) -> bytes:
        """将 PDG 二进制数据解码为标准 ITU-T CCITT Group 4 TIFF 或保留标准 JPEG/PNG"""
        # 兼容 PNG（若带透明通道或隔行扫描，先扁平化以防 img2pdf 整本合并失败）
        if raw_bytes.startswith(b'\x89PNG'):
            try:
                with Image.open(io.BytesIO(raw_bytes)) as im:
                    if im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info or im.info.get('interlace'):
                        if im.mode in ('RGBA', 'LA', 'PA', 'P'):
                            bg = Image.new('RGB', im.size, (255, 255, 255))
                            rgba = im.convert('RGBA')
                            bg.paste(rgba, mask=rgba.split()[-1])
                            im_out = bg
                        else:
                            im_out = im.convert('RGB')
                        out_buf = io.BytesIO()
                        im_out.save(out_buf, format='PNG')
                        return out_buf.getvalue()
            except Exception:
                pass
            return raw_bytes

        # 兼容 BMP 格式封面/插页
        if raw_bytes.startswith(b'BM'):
            with Image.open(io.BytesIO(raw_bytes)) as im:
                out_buf = io.BytesIO()
                target_mode = im.mode if im.mode in ('1', 'L', 'RGB') else 'RGB'
                im.convert(target_mode).save(out_buf, format='PNG')
                return out_buf.getvalue()

        # 如果本身已是标准图片 (JPEG / TIFF)
        if raw_bytes.startswith((b'\xff\xd8', b'II\x2a\x00', b'MM\x00\x2a')):
            return raw_bytes

        data_ptr = self.malloc(self.store, len(raw_bytes))
        if not data_ptr:
            raise MemoryError("WASM malloc 分配内存失败")

        bitmap_ptr = 0
        try:
            self.memory.write(self.store, raw_bytes, data_ptr)

            width = self.pdg_get_width(self.store, data_ptr, len(raw_bytes))
            height = self.pdg_get_height(self.store, data_ptr, len(raw_bytes))

            if width <= 0 or height <= 0:
                raise ValueError(f"异常图像尺寸: {width}x{height}")

            bitmap_ptr = self.pdg_alloc_bitmap(self.store, width, height)
            if not bitmap_ptr:
                raise MemoryError("WASM pdg_alloc_bitmap 分配位图内存失败")

            row_words = (width >> 5) + (1 if (width & 31) != 0 else 0)
            row_bytes = row_words * 4
            bitmap_size = row_bytes * height

            ret = self.pdg_decode_file(self.store, data_ptr, len(raw_bytes), bitmap_ptr, bitmap_size)
            if ret != 0:
                raise ValueError(f"PDG 解码失败 (错误码: {ret})")

            raw_bitmap = bytes(self.memory.read(self.store, bitmap_ptr, bitmap_ptr + bitmap_size))

            # 使用查表法极速反色 (PDG 解码输出为前景点，反转后 0=黑/文字, 1=白/背景)
            inv_data = raw_bitmap.translate(_INV_TABLE)
            img = Image.frombytes('1', (row_bytes * 8, height), inv_data, 'raw', '1;I')
            if img.size != (width, height):
                img = img.crop((0, 0, width, height))

            # 保存为标准 ITU-T CCITT Group 4 TIFF 供 img2pdf 极速无损封装
            buf = io.BytesIO()
            img.save(buf, format='TIFF', compression='group4')
            return buf.getvalue()
        finally:
            if data_ptr:
                self.free(self.store, data_ptr)
            if bitmap_ptr:
                self.pdg_free(self.store, bitmap_ptr)


def parse_pdg_bytes(raw_bytes: bytes) -> bytes:
    """将单个 PDG 字节流解码为标准 TIFF/PNG/JPEG 字节流"""
    session = PdgDecoderSession()
    return session.decode_to_standard_tiff(raw_bytes)


# ============================================================================
# PDG Page & Sorting
# ============================================================================

class PdgPage:
    """PDG 页面数据对象"""

    def __init__(self, filename: str, data: bytes, has_bac: bool = False):
        self.filename = filename
        self.data = data
        self.sort_tuple = self._compute_sort_key(filename, has_bac=has_bac)
        self.page_type, self.page_num, _ = self.sort_tuple

    @staticmethod
    def _compute_sort_key(filename: str, has_bac: bool = False) -> Tuple[int, int, str]:
        """
        计算超星 PDG 页面的标准阅读排序键:
          0: cov (封面)
          1: bok (书名页)
          2: leg (版权页)
          3: fow / pre / prf (前言)
          4: ! (!00001 等目录/前置图)
          5: toc / dir / cat (目录)
          6: 数字 / cnt (000001 等正文)
          7: 其他未分类
          8: att / app / ins (附录)
          9: bac (封底；若包内无 bac 且存在 cov002/cov2，也归为封底)
        """
        base = os.path.basename(filename).lower()
        for ext in VALID_PAGE_EXTS:
            if base.endswith(ext):
                base = base[:-len(ext)]
                break
        name = base

        # 9. 封底 (bac；若包内无独立 bac 文件，超星习惯用 cov002/cov2 表示封底)
        if name.startswith('bac'):
            m = re.search(r'\d+', name)
            return (9, int(m.group()) if m else 1, name)
        if not has_bac and name in ('cov002', 'cov2'):
            m = re.search(r'\d+', name)
            return (9, int(m.group()) if m else 2, name)

        # 0. 封面 (cov / cover)
        if name.startswith('cov'):
            m = re.search(r'\d+', name)
            return (0, int(m.group()) if m else 1, name)

        # 1. 书名页 (bok / title)
        if name.startswith('bok') or name.startswith('title'):
            m = re.search(r'\d+', name)
            return (1, int(m.group()) if m else 1, name)

        # 2. 版权页 (leg / cpy)
        if name.startswith('leg') or name.startswith('cpy'):
            m = re.search(r'\d+', name)
            return (2, int(m.group()) if m else 1, name)

        # 3. 前言 / 序言 (fow / pre / prf)
        if name.startswith('fow') or name.startswith('pre') or name.startswith('prf'):
            m = re.search(r'\d+', name)
            return (3, int(m.group()) if m else 1, name)

        # 4. ! 前缀 (!00001, !00002 等目录/前置图)
        if name.startswith('!'):
            m = re.search(r'\d+', name)
            return (4, int(m.group()) if m else 0, name)

        # 5. 目录页 (toc / dir / cat)
        if name.startswith('toc') or name.startswith('dir') or name.startswith('cat'):
            m = re.search(r'\d+', name)
            return (5, int(m.group()) if m else 1, name)

        # 6. 正文页 (纯数字如 000001 或 cnt 前缀)
        if name.isdigit():
            return (6, int(name), name)
        if name.startswith('cnt') and name[3:].isdigit():
            return (6, int(name[3:]), name)

        # 8. 附录 / 插页 (att / app / ins)
        if name.startswith('att') or name.startswith('app') or name.startswith('ins'):
            m = re.search(r'\d+', name)
            return (8, int(m.group()) if m else 1, name)

        # 7. 其他未分类格式
        m = re.search(r'\d+', name)
        return (7, int(m.group()) if m else 0, name)


# ============================================================================
# Metadata & Bookmarks (TOC) Extraction
# ============================================================================

def parse_bookinfo(data: bytes) -> Dict[str, str]:
    """解析 bookinfo.dat / 书籍元数据"""
    info = {}
    for encoding in ('gb18030', 'gbk', 'utf-8', 'latin1'):
        try:
            text = data.decode(encoding)
            for line in text.splitlines():
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    info[k.strip()] = v.strip()
            if info:
                break
        except Exception:
            continue
    return info


def parse_bookcontents(data: bytes) -> List[Dict[str, Any]]:
    """解析 BookContents.dat 目录大纲数据（支持 zlib 压缩格式）"""
    decomp = None
    for header in (b'\x78\x9c', b'\x78\xda', b'\x78\x01', b'\x78\x5e'):
        idx = data.find(header)
        if idx >= 0:
            try:
                decomp = zlib.decompress(data[idx:])
                break
            except Exception:
                continue

    if not decomp:
        decomp = data

    entries = []
    for encoding in ('gb18030', 'gbk', 'utf-8'):
        try:
            text = decomp.decode(encoding)
            for line in text.splitlines():
                line = line.strip()
                if not line or '|' not in line:
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    title = parts[0].strip()
                    level_code = parts[1].strip()
                    try:
                        page_num = int(parts[2].strip())
                    except ValueError:
                        page_num = 1
                    page_type = int(parts[4].strip()) if len(parts) > 4 and parts[4].strip().isdigit() else 6
                    raw_len = len(level_code)
                    level = 0 if raw_len <= 4 else (raw_len - 4) // 2

                    if title:
                        entries.append({
                            'title': title,
                            'level': level,
                            'page_num': page_num,
                            'page_type': page_type
                        })
            if entries:
                break
        except Exception:
            continue

    return entries


# ============================================================================
# Core Converter
# ============================================================================

class PdgConverter:
    """PDG 批量转 PDF 转换器"""

    def __init__(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        dpi: float = 200.0,
        password: Optional[str] = None,
        pwd_file: Optional[str] = None,
        fit_width: bool = True,
        show_progress: bool = True,
        interactive: bool = True,
        verbose: bool = True,
    ):
        self.input_path = os.path.abspath(input_path)
        self.dpi = dpi
        self.password = password
        self.pwd_file = pwd_file
        self.fit_width = fit_width
        self.show_progress = show_progress
        self.interactive = interactive
        self.verbose = verbose
        if output_path and os.path.isdir(output_path):
            base_name = os.path.splitext(os.path.basename(self.input_path.rstrip('/\\')))[0]
            self.output_path = os.path.join(output_path, f"{base_name}.pdf")
        else:
            self.output_path = output_path or self._default_output_path(self.input_path)
        self.metadata: Dict[str, str] = {}
        self.toc_entries: List[Dict[str, Any]] = []

    def _log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    @staticmethod
    def _default_output_path(input_path: str) -> str:
        clean_path = input_path.rstrip('/\\')
        base_name = os.path.splitext(os.path.basename(clean_path))[0]
        parent_dir = os.path.dirname(clean_path)
        return os.path.join(parent_dir, f"{base_name}.pdf")

    def _load_password_candidates(self) -> List[str]:
        candidates: List[str] = []
        seen = set()

        def add_pwd(s: str):
            s = s.rstrip('\r\n')
            if s and s not in seen:
                seen.add(s)
                candidates.append(s)

        if self.pwd_file:
            if not os.path.exists(self.pwd_file):
                raise FileNotFoundError(f"密码字典文件不存在: {self.pwd_file}")
            with open(self.pwd_file, 'rb') as f:
                raw_bytes = f.read()
            text = None
            for enc in ('utf-8-sig', 'gb18030', 'latin1'):
                try:
                    text = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text:
                for line in text.splitlines():
                    add_pwd(line)

        for pwd in COMMON_ZIP_PASSWORDS:
            add_pwd(pwd)

        return candidates

    def _open_zip_and_unlock(self):
        """打开 ZIP 并自动处理加密（支持 ZipCrypto、AES 及 UTF-8/GB18030 密码）"""
        def filter_infos(archive):
            return [
                i for i in archive.infolist()
                if not i.is_dir()
                and not i.filename.replace('\\', '/').startswith('__MACOSX')
                and not i.filename.replace('\\', '/').endswith('/')
            ]

        def try_read_with_pwd(archive, test_info, pwd_str: str) -> Optional[bytes]:
            encoded_list: List[bytes] = []
            for enc in ('utf-8', 'gb18030'):
                try:
                    b = pwd_str.encode(enc)
                    if b not in encoded_list:
                        encoded_list.append(b)
                except UnicodeEncodeError:
                    continue

            for pwd_bytes in encoded_list:
                try:
                    archive.read(test_info, pwd=pwd_bytes)
                    return pwd_bytes
                except NotImplementedError:
                    raise
                except _ZIP_PWD_ERRORS:
                    continue
            return None

        zf = zipfile.ZipFile(self.input_path, 'r')
        infos = filter_infos(zf)
        encrypted_infos = [i for i in infos if i.flag_bits & 0x1]
        if not encrypted_infos:
            return zf, infos, None

        test_info = min(encrypted_infos, key=lambda i: i.file_size)

        try:
            if self.password is not None:
                matched = try_read_with_pwd(zf, test_info, self.password)
                if matched is not None:
                    return zf, infos, matched
                zf.close()
                raise ValueError("提供的 ZIP 解压密码不正确")

            pwd_list = self._load_password_candidates()
            self._log(f"🔐 检测到加密 ZIP，正在尝试常用密码库 ({len(pwd_list)} 个)...")
            for candidate in pwd_list:
                matched = try_read_with_pwd(zf, test_info, candidate)
                if matched is not None:
                    self._log(f"🔓 成功匹配解压密码: {candidate}")
                    return zf, infos, matched
        except NotImplementedError:
            zf.close()
            if not HAS_PYZIPPER:
                raise RuntimeError(
                    "该 ZIP 使用了 AES 加密，Python 内置 zipfile 不支持。\n"
                    "请先安装 pyzipper: pip install pyzipper"
                )
            zf = pyzipper.AESZipFile(self.input_path, 'r')
            infos = filter_infos(zf)
            encrypted_infos = [i for i in infos if i.flag_bits & 0x1]
            test_info = min(encrypted_infos, key=lambda i: i.file_size)

            if self.password is not None:
                matched = try_read_with_pwd(zf, test_info, self.password)
                if matched is not None:
                    return zf, infos, matched
                zf.close()
                raise ValueError("提供的 ZIP 解压密码不正确")

            pwd_list = self._load_password_candidates()
            self._log(f"🔐 检测到 AES 加密 ZIP，正在尝试常用密码库 ({len(pwd_list)} 个)...")
            for candidate in pwd_list:
                matched = try_read_with_pwd(zf, test_info, candidate)
                if matched is not None:
                    self._log(f"🔓 成功匹配解压密码: {candidate}")
                    return zf, infos, matched

        if self.interactive and sys.stdin.isatty():
            manual_pwd = getpass.getpass("🔑 密码库未命中，请输入 ZIP 解压密码: ")
            if manual_pwd:
                matched = try_read_with_pwd(zf, test_info, manual_pwd)
                if matched is not None:
                    return zf, infos, matched

        zf.close()
        raise ValueError("ZIP 已加密且未匹配到正确密码，请使用 -p <密码> 或 --pwd-file <密码字典> 指定")

    def _collect_from_zip(self) -> List[Tuple[str, bytes]]:
        pdg_items = []
        zf, infos, matched_pwd = self._open_zip_and_unlock()
        try:
            for info in infos:
                norm_path = info.filename.replace('\\', '/')
                fname = norm_path.rsplit('/', 1)[-1]
                fname_lower = fname.lower()
                pwd_arg = matched_pwd if (info.flag_bits & 0x1) else None

                if any(fname_lower.endswith(ext) for ext in VALID_PAGE_EXTS):
                    pdg_items.append((fname, zf.read(info, pwd=pwd_arg)))
                elif fname_lower in ('bookinfo.dat', 'bookinfo.txt'):
                    self.metadata = parse_bookinfo(zf.read(info, pwd=pwd_arg))
                elif 'bookcontents' in fname_lower:
                    self.toc_entries = parse_bookcontents(zf.read(info, pwd=pwd_arg))
        finally:
            zf.close()

        return pdg_items

    def _collect_from_dir(self) -> List[Tuple[str, bytes]]:
        pdg_items = []
        for root, _, files in os.walk(self.input_path):
            for file in files:
                if file.startswith('.'):
                    continue
                fpath = os.path.join(root, file)
                fname_lower = file.lower()
                if any(fname_lower.endswith(ext) for ext in VALID_PAGE_EXTS):
                    with open(fpath, 'rb') as f:
                        pdg_items.append((file, f.read()))
                elif fname_lower in ('bookinfo.dat', 'bookinfo.txt'):
                    with open(fpath, 'rb') as f:
                        self.metadata = parse_bookinfo(f.read())
                elif 'bookcontents' in fname_lower:
                    with open(fpath, 'rb') as f:
                        self.toc_entries = parse_bookcontents(f.read())

        return pdg_items

    def convert(self) -> str:
        """执行完整转换流程"""
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"输入路径不存在: {self.input_path}")

        self._log(f"📖 正在扫描输入源: {self.input_path}")

        if zipfile.is_zipfile(self.input_path):
            raw_entries = self._collect_from_zip()
        elif os.path.isdir(self.input_path):
            raw_entries = self._collect_from_dir()
        elif any(self.input_path.lower().endswith(ext) for ext in VALID_PAGE_EXTS):
            with open(self.input_path, 'rb') as f:
                raw_entries = [(os.path.basename(self.input_path), f.read())]
        else:
            raise ValueError(f"不支持的输入格式: {self.input_path}")

        if not raw_entries:
            raise ValueError("未在输入路径中找到任何有效的书籍页面文件 (.pdg / .png / .jpg 等)")

        self._log(f"📦 发现 {len(raw_entries)} 个页面文件")
        if self.metadata:
            title = self.metadata.get('书名') or self.metadata.get('title', '')
            author = self.metadata.get('作者') or self.metadata.get('author', '')
            self._log(f"📋 书籍信息: 《{title}》 | 作者: {author}")

        # 判断书内是否包含独立 bac 封底文件，并按标准阅读优先级排序
        has_bac = any(os.path.basename(name).lower().startswith('bac') for name, _ in raw_entries)
        parsed_pages: List[PdgPage] = [PdgPage(name, data, has_bac=has_bac) for name, data in raw_entries]
        parsed_pages.sort(key=lambda p: p.sort_tuple)

        # 计算各区域在 PDF 中的物理索引 (0-indexed)
        body_start_index = 0
        toc_start_index = None
        fow_start_index = None
        for idx, p in enumerate(parsed_pages):
            ptype = p.sort_tuple[0]
            if ptype == 3 and fow_start_index is None:
                fow_start_index = idx
            elif ptype in (4, 5) and toc_start_index is None:
                toc_start_index = idx
            elif ptype >= 6:
                body_start_index = idx
                break

        # 初始化解码会话
        session = PdgDecoderSession()

        # 逐页高精度解码为标准 CCITT G4 TIFF
        image_stream_list: List[bytes] = []
        for p in tqdm(
            parsed_pages,
            desc="🖼️ 解码 PDG 并封装标准 TIFF",
            unit="页",
            disable=not self.show_progress,
        ):
            try:
                tiff_bytes = session.decode_to_standard_tiff(p.data)
                image_stream_list.append(tiff_bytes)
            except Exception as e:
                self._log(f"\n⚠️ 页面 {p.filename} 解码异常: {e}")
                img = Image.new('1', (1500, 2000), color=1)
                buf = io.BytesIO()
                img.save(buf, format='TIFF', compression='group4')
                image_stream_list.append(buf.getvalue())

        # 校验页面尺寸：统计正文/正常页尺寸，自动修复极小占位图 (如 1x1) 或读取异常页
        min_px = math.ceil(3.0 * self.dpi / 72.0) + 1
        page_sizes: List[Optional[Tuple[int, int]]] = []
        body_widths: List[int] = []
        body_heights: List[int] = []
        valid_widths: List[int] = []
        valid_heights: List[int] = []

        for idx, img_bytes in enumerate(image_stream_list):
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    w, h = im.size
                page_sizes.append((w, h))
                if w >= min_px and h >= min_px:
                    valid_widths.append(w)
                    valid_heights.append(h)
                    if parsed_pages[idx].sort_tuple[0] == 6:
                        body_widths.append(w)
                        body_heights.append(h)
            except Exception as e:
                self._log(f"⚠️ 页面 {parsed_pages[idx].filename} 图像读取异常 ({e})，已替换为空白页")
                page_sizes.append(None)

        ref_widths = body_widths or valid_widths
        ref_heights = body_heights or valid_heights
        med_w = sorted(ref_widths)[len(ref_widths) // 2] if ref_widths else 1200
        med_h = sorted(ref_heights)[len(ref_heights) // 2] if ref_heights else 1600

        for idx, size in enumerate(page_sizes):
            if size is None or size[0] < min_px or size[1] < min_px:
                fname = parsed_pages[idx].filename
                if size is None:
                    canvas = Image.new('1', (med_w, med_h), color=1)
                    buf = io.BytesIO()
                    canvas.save(buf, format='TIFF', compression='group4')
                    image_stream_list[idx] = buf.getvalue()
                else:
                    w, h = size
                    self._log(f"⚠️ 页面 {fname} 像素尺寸过小 ({w}x{h})，已自动补白适配标准页面")
                    if w < min_px and h < min_px:
                        new_w, new_h = med_w, med_h
                    else:
                        new_w, new_h = max(w, min_px), max(h, min_px)
                    with Image.open(io.BytesIO(image_stream_list[idx])) as orig_im:
                        mode = orig_im.mode if orig_im.mode in ('1', 'L', 'RGB') else 'RGB'
                        bg_color = 1 if mode == '1' else (255 if mode == 'L' else (255, 255, 255))
                        canvas = Image.new(mode, (new_w, new_h), color=bg_color)
                        canvas.paste(orig_im.convert(mode), ((new_w - w) // 2, (new_h - h) // 2))
                        buf = io.BytesIO()
                        if mode == '1':
                            canvas.save(buf, format='TIFF', compression='group4')
                        else:
                            canvas.save(buf, format='PNG')
                        image_stream_list[idx] = buf.getvalue()

        # 步骤 1: 使用 img2pdf 极速无损合并生成初始 PDF
        self._log("⚡ 正在合并生成 PDF (img2pdf 极速无损通道)...")
        target_w_pt = med_w * 72.0 / self.dpi
        target_h_pt = med_h * 72.0 / self.dpi

        def safe_layout_fun(imgwidthpx: int, imgheightpx: int, _ndpi) -> Tuple[float, float, float, float]:
            if self.fit_width:
                # 竖版页面（含封面/彩页）统一对齐正文宽度；横版跨页则对齐高度，无损不重采样
                if imgwidthpx > imgheightpx and imgwidthpx > med_w * 1.3:
                    pt_h = target_h_pt
                    pt_w = imgwidthpx * target_h_pt / max(imgheightpx, 1)
                else:
                    pt_w = target_w_pt
                    pt_h = imgheightpx * target_w_pt / max(imgwidthpx, 1)
            else:
                pt_w = imgwidthpx * 72.0 / self.dpi
                pt_h = imgheightpx * 72.0 / self.dpi

            max_pt = max(pt_w, pt_h)
            if max_pt > 14400.0:
                scale = 14400.0 / max_pt
                pt_w *= scale
                pt_h *= scale
            if pt_w < 3.0 or pt_h < 3.0:
                scale = max(3.0 / max(pt_w, 1e-6), 3.0 / max(pt_h, 1e-6))
                pt_w = min(14400.0, pt_w * scale)
                pt_h = min(14400.0, pt_h * scale)
            return pt_w, pt_h, pt_w, pt_h

        pdf_bytes = img2pdf.convert(
            image_stream_list,
            layout_fun=safe_layout_fun,
            rotation=img2pdf.Rotation.ifvalid,
        )

        # 步骤 2: 使用 pikepdf 注入元数据及目录书签 (Outline / Bookmarks)
        self._log("📑 正在注入元数据与目录大纲书签...")
        pdf = pikepdf.open(io.BytesIO(pdf_bytes))
        total_pages = len(pdf.pages)

        # 注入元数据
        try:
            with pdf.open_metadata() as meta:
                title = self.metadata.get('书名') or self.metadata.get('title', '')
                author = self.metadata.get('作者') or self.metadata.get('author', '')
                date = self.metadata.get('出版日期') or self.metadata.get('date', '')
                if title:
                    meta['dc:title'] = title
                if author:
                    meta['dc:creator'] = [author]
                if date:
                    meta['dc:date'] = date
        except Exception as e:
            self._log(f"⚠️ 元数据写入提示: {e}")

        # 注入书签大纲 (Outlines)
        if self.toc_entries:
            try:
                with pdf.open_outline() as outline:
                    stack = [(0, outline.root)]

                    for entry in self.toc_entries:
                        title = entry['title']
                        level = entry['level']
                        page_num = entry['page_num']
                        page_type = entry.get('page_type', 6)

                        if page_type == 6:  # 正文
                            target_page_idx = body_start_index + (page_num - 1)
                        elif page_type == 5:  # 目录
                            target_page_idx = toc_start_index if toc_start_index is not None else max(0, body_start_index - 1)
                        elif page_type == 4:  # 前言
                            target_page_idx = fow_start_index if fow_start_index is not None else max(0, body_start_index - 2)
                        elif page_type == 1:  # 封面
                            target_page_idx = 0
                        else:
                            target_page_idx = min(page_num - 1, total_pages - 1)

                        target_page_idx = max(0, min(target_page_idx, total_pages - 1))
                        item = pikepdf.OutlineItem(title, target_page_idx)

                        while len(stack) > 1 and stack[-1][0] >= level + 1:
                            stack.pop()

                        stack[-1][1].append(item)
                        stack.append((level + 1, item.children))

                self._log(f"✅ 成功注入 {len(self.toc_entries)} 条目录大纲书签")
            except Exception as e:
                self._log(f"⚠️ 书签生成提示: {e}")

        # 保存输出
        os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)
        pdf.save(self.output_path)
        pdf.close()

        file_size_mb = os.path.getsize(self.output_path) / (1024 * 1024)
        self._log(f"\n🎉 转换完成: {self.output_path}")
        self._log(f"📊 总页数: {total_pages} 页 | 文件大小: {file_size_mb:.2f} MB")
        return self.output_path


# ============================================================================
# Batch Processing & Target Scanner
# ============================================================================

def _is_single_book_dir(dir_path: str) -> bool:
    """
    检查目录下是否为解压后的单本图书目录。
    特征：包含 bookinfo.dat/bookinfo.txt，或包含标准书页命名的文件（如 000001/!00001/cov 等），
    或直接包含多个页面文件（>= 3 页）。
    """
    try:
        page_count = 0
        with os.scandir(dir_path) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                name_lower = entry.name.lower()
                if name_lower in ('bookinfo.dat', 'bookinfo.txt') or 'bookcontents' in name_lower:
                    return True
                if any(name_lower.endswith(ext) for ext in VALID_PAGE_EXTS):
                    stem = os.path.splitext(name_lower)[0]
                    # 超星标准前缀或 4 位以上纯数字正文页
                    if re.match(r'^(!|cov|bok|leg|fow|pre|prf|toc|dir|cat|att|app|ins|bac|\d{4,})', stem):
                        return True
                    page_count += 1
                    if page_count >= 3:
                        return True
    except OSError:
        pass
    return False


def scan_book_targets(
    inputs: Union[str, List[str]],
    recursive: bool = False,
    batch_mode: bool = False,
) -> List[str]:
    """
    扫描并收集所有待转换的书籍目标（ZIP 压缩包、包含 PDG/图像 的子目录或单个 PDG/图像文件）。
    """
    if isinstance(inputs, str):
        raw_inputs = [inputs]
    else:
        raw_inputs = list(inputs)

    # 展开通配符（适配 Windows 或 API 调用场景）
    expanded_inputs: List[str] = []
    for item in raw_inputs:
        if any(c in item for c in ('*', '?', '[')):
            matched = glob.glob(item, recursive=recursive)
            if matched:
                expanded_inputs.extend(matched)
            else:
                expanded_inputs.append(item)
        else:
            expanded_inputs.append(item)

    effective_batch = batch_mode or len(expanded_inputs) > 1

    # 若单个目录未指定 -b，但包含 ZIP 文件或多个图书子目录，则自动启用批处理模式
    if not effective_batch and len(expanded_inputs) == 1 and os.path.isdir(expanded_inputs[0]):
        single_dir = expanded_inputs[0]
        if not _is_single_book_dir(single_dir):
            try:
                with os.scandir(single_dir) as it:
                    entries = list(it)
                    has_zips = any(e.is_file() and e.name.lower().endswith('.zip') for e in entries)
                    sub_books = any(e.is_dir() and _is_single_book_dir(e.path) for e in entries)
                    if has_zips or sub_books:
                        effective_batch = True
                        print(f"💡 检测到目录中包含多个电子书文件/子目录，自动启用批处理模式: {single_dir}")
            except OSError:
                pass

    targets: List[str] = []

    for item in expanded_inputs:
        if not os.path.exists(item):
            print(f"⚠️ 路径不存在，已忽略: {item}")
            continue

        item_abs = os.path.abspath(item)

        if os.path.isfile(item_abs):
            lower = item_abs.lower()
            if lower.endswith(('.zip', *VALID_PAGE_EXTS)) or zipfile.is_zipfile(item_abs):
                targets.append(item_abs)
            else:
                print(f"⚠️ 忽略非支持文件: {item}")
        elif os.path.isdir(item_abs):
            if not effective_batch:
                targets.append(item_abs)
            else:
                if recursive:
                    for root, dirs, files in os.walk(item_abs):
                        for f in sorted(files):
                            if f.lower().endswith('.zip') and not f.startswith('.'):
                                targets.append(os.path.join(root, f))
                        if _is_single_book_dir(root):
                            targets.append(root)
                else:
                    try:
                        with os.scandir(item_abs) as it:
                            entries = sorted(list(it), key=lambda e: e.name)
                            for entry in entries:
                                if entry.name.startswith('.'):
                                    continue
                                if entry.is_file() and entry.name.lower().endswith('.zip'):
                                    targets.append(entry.path)
                                elif entry.is_dir() and _is_single_book_dir(entry.path):
                                    targets.append(entry.path)
                    except OSError as e:
                        print(f"⚠️ 扫描目录异常 ({item}): {e}")

                    if _is_single_book_dir(item_abs) and item_abs not in targets:
                        targets.append(item_abs)

    seen = set()
    unique_targets: List[str] = []
    for t in targets:
        norm = os.path.normpath(t)
        if norm not in seen:
            seen.add(norm)
            unique_targets.append(t)

    return unique_targets


def resolve_output_path(
    target: str,
    output_arg: Optional[str] = None,
    total_targets: int = 1,
) -> str:
    """计算单个书籍目标的输出 PDF 路径"""
    target_abs = os.path.abspath(target)
    clean_target = target_abs.rstrip('/\\')
    if os.path.isfile(target_abs):
        stem = os.path.splitext(os.path.basename(target_abs))[0]
    else:
        stem = os.path.basename(clean_target)

    if not output_arg:
        parent = os.path.dirname(clean_target)
        return os.path.join(parent, f"{stem}.pdf")

    output_abs = os.path.abspath(output_arg)

    if total_targets == 1:
        if output_abs.lower().endswith('.pdf'):
            return output_abs
        else:
            return os.path.join(output_abs, f"{stem}.pdf")
    else:
        if output_abs.lower().endswith('.pdf'):
            out_dir = os.path.dirname(output_abs)
        else:
            out_dir = output_abs
        return os.path.join(out_dir, f"{stem}.pdf")


class BatchItemResult:
    """批处理单个任务结果"""

    def __init__(
        self,
        input_path: str,
        output_path: Optional[str],
        status: str,  # 'success', 'skipped', 'failed'
        error: Optional[str] = None,
        duration: float = 0.0,
    ):
        self.input_path = input_path
        self.output_path = output_path
        self.status = status
        self.error = error
        self.duration = duration

    def __repr__(self) -> str:
        return f"<BatchItemResult status={self.status} input={os.path.basename(self.input_path)} duration={self.duration:.2f}s>"


class BatchResult:
    """批处理总体统计结果"""

    def __init__(self, items: List[BatchItemResult], total_time: float):
        self.items = items
        self.total_time = total_time

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> List[BatchItemResult]:
        return [item for item in self.items if item.status == 'success']

    @property
    def skipped(self) -> List[BatchItemResult]:
        return [item for item in self.items if item.status == 'skipped']

    @property
    def failed(self) -> List[BatchItemResult]:
        return [item for item in self.items if item.status == 'failed']

    def print_summary(self):
        print("\n" + "=" * 62)
        print("📊 批处理转换完成统计")
        print("=" * 62)
        print(f"📁 目标总计: {self.total} 本")
        print(f"✅ 转换成功: {len(self.succeeded)} 本")
        if self.skipped:
            print(f"⏭️ 跳过已有: {len(self.skipped)} 本")
        if self.failed:
            print(f"❌ 转换失败: {len(self.failed)} 本")
            for item in self.failed:
                name = os.path.basename(item.input_path)
                print(f"   • {name}: {item.error}")
        mins = int(self.total_time // 60)
        secs = self.total_time % 60
        time_str = f"{mins} 分 {secs:.1f} 秒" if mins > 0 else f"{secs:.2f} 秒"
        print(f"⏱️ 总体耗时: {time_str}")
        print("=" * 62)


def batch_convert(
    inputs: Union[str, List[str]],
    output_dir: Optional[str] = None,
    dpi: float = 200.0,
    password: Optional[str] = None,
    pwd_file: Optional[str] = None,
    fit_width: bool = True,
    recursive: bool = False,
    skip_existing: bool = False,
    workers: int = 1,
    show_progress: bool = True,
    interactive: bool = False,
) -> BatchResult:
    """
    批量将超星 PDG 书籍转换为 PDF。

    :param inputs: 单个或多个输入路径（文件、目录或通配符列表）
    :param output_dir: 输出目录路径（可选，默认输出到各目标源文件同目录）
    :param dpi: 渲染分辨率 DPI (默认: 200.0)
    :param password: ZIP 解压密码（可选）
    :param pwd_file: 密码字典文件路径（可选）
    :param fit_width: 是否开启正文页宽对齐
    :param recursive: 是否递归扫描子目录
    :param skip_existing: 若输出文件已存在且非空，是否跳过转换
    :param workers: 并发工作线程数（默认 1 为顺序执行）
    :param show_progress: 是否显示单书内的页面解码进度条
    :param interactive: 密码未命中时是否在终端进行交互式询问
    :return: BatchResult 对象
    """
    targets = scan_book_targets(inputs, recursive=recursive, batch_mode=True)
    if not targets:
        print("⚠️ 未找到任何待转换的书籍目标 (ZIP 压缩包或包含 PDG 的文件夹)")
        return BatchResult([], 0.0)

    total_count = len(targets)
    print("\n" + "=" * 62)
    print(f"📚 开始批处理转换 (共发现 {total_count} 本书籍)")
    if output_dir:
        resolved_out_dir = os.path.abspath(output_dir)
        if resolved_out_dir.lower().endswith('.pdf'):
            resolved_out_dir = os.path.dirname(resolved_out_dir)
        os.makedirs(resolved_out_dir, exist_ok=True)
        print(f"📂 输出目录: {resolved_out_dir}")
    print("=" * 62)

    start_time = time.time()
    items: List[BatchItemResult] = []

    if workers <= 1:
        # 单线程顺序执行
        for idx, target in enumerate(targets, start=1):
            out_path = resolve_output_path(target, output_dir, total_count)
            book_name = os.path.basename(target)
            print(f"\n[{idx}/{total_count}] 📖 正在处理: {book_name}")

            if skip_existing and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                print(f"⏭️ 目标文件已存在且非空，跳过转换: {out_path}")
                items.append(BatchItemResult(target, out_path, 'skipped'))
                continue

            t0 = time.time()
            try:
                converter = PdgConverter(
                    target,
                    output_path=out_path,
                    dpi=dpi,
                    password=password,
                    pwd_file=pwd_file,
                    fit_width=fit_width,
                    show_progress=show_progress,
                    interactive=interactive,
                    verbose=True,
                )
                converter.convert()
                elapsed = time.time() - t0
                items.append(BatchItemResult(target, out_path, 'success', duration=elapsed))
            except Exception as e:
                elapsed = time.time() - t0
                print(f"❌ 《{book_name}》转换失败 ({elapsed:.1f}s): {e}")
                items.append(BatchItemResult(target, out_path, 'failed', error=str(e), duration=elapsed))
    else:
        # 多线程并发执行
        import concurrent.futures
        print(f"⚡ 启用多线程并发加速，并发线程数: {workers}")
        print_lock = threading.Lock()
        completed_count = 0
        stop_event = threading.Event()

        def process_one(task_data: Tuple[int, str, str]) -> BatchItemResult:
            nonlocal completed_count
            task_idx, target, out_path = task_data
            if stop_event.is_set():
                return BatchItemResult(target, out_path, 'cancelled', error="用户取消")

            book_name = os.path.basename(target)

            if skip_existing and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                with print_lock:
                    completed_count += 1
                    print(f"⏭️ [{completed_count}/{total_count}] 跳过已存在: {book_name}")
                return BatchItemResult(target, out_path, 'skipped')

            with print_lock:
                print(f"🚀 开始转换 [{task_idx}/{total_count}]: {book_name}")

            t0 = time.time()
            try:
                converter = PdgConverter(
                    target,
                    output_path=out_path,
                    dpi=dpi,
                    password=password,
                    pwd_file=pwd_file,
                    fit_width=fit_width,
                    show_progress=False,
                    interactive=False,
                    verbose=False,
                )
                converter.convert()
                elapsed = time.time() - t0
                with print_lock:
                    completed_count += 1
                    print(f"✅ [{completed_count}/{total_count}] 转换成功 ({elapsed:.1f}s): {book_name} -> {os.path.basename(out_path)}")
                return BatchItemResult(target, out_path, 'success', duration=elapsed)
            except Exception as e:
                elapsed = time.time() - t0
                with print_lock:
                    completed_count += 1
                    print(f"❌ [{completed_count}/{total_count}] 转换失败 ({elapsed:.1f}s): {book_name} ({e})")
                return BatchItemResult(target, out_path, 'failed', error=str(e), duration=elapsed)

        task_list = [
            (i + 1, target, resolve_output_path(target, output_dir, total_count))
            for i, target in enumerate(targets)
        ]
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            items = list(executor.map(process_one, task_list))
        except KeyboardInterrupt:
            stop_event.set()
            executor.shutdown(wait=False, cancel_futures=True)
            print("\n❌ 用户取消批处理操作")
            sys.exit(130)
        finally:
            executor.shutdown(wait=False)

    total_time = time.time() - start_time
    result = BatchResult(items, total_time)
    result.print_summary()
    return result


# ============================================================================
# CLI Command Line Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="PDG to PDF 转换工具 (超星 PDG 格式)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 单本图书转换
  pdg2pdf book.zip                       # ZIP 压缩包转 PDF（自动尝试常用密码）
  pdg2pdf book.zip -p 28zrs              # 指定 ZIP 解压密码
  pdg2pdf book.zip --pwd-file pwds.txt   # 指定外挂密码字典文件
  pdg2pdf book.zip -o output.pdf         # 指定输出路径
  pdg2pdf ./book_folder/                 # 文件夹转 PDF
  pdg2pdf 000001.pdg                     # 单页 PDG 转换
  pdg2pdf book.zip --dpi 300             # 自定义 DPI 分辨率

  # 批处理转换
  pdg2pdf *.zip -o ./output/             # 批量转换所有 ZIP 电子书到 output 目录
  pdg2pdf book1.zip book2.zip folder1/   # 同时传入多个文件/目录批量转换
  pdg2pdf -b ./books/ -o ./output/       # 批量扫描目录下的所有书籍进行转换
  pdg2pdf -b ./books/ -r                 # 递归扫描所有子目录中的书籍
  pdg2pdf -b ./books/ -s                 # 跳过已存在的 PDF (支持断点续转)
  pdg2pdf -b ./books/ -w 4               # 4 线程并发加速批量转换
"""
    )

    parser.add_argument("inputs", nargs="+", help="输入路径，支持传入一个或多个文件/目录/通配符")
    parser.add_argument("-o", "--output", help="输出路径 (单书转换时为 PDF 文件路径，批处理时为输出目录)")
    parser.add_argument("-b", "--batch", action="store_true", help="强制启用批处理模式 (扫描目录下的所有 ZIP 与书籍子目录)")
    parser.add_argument("-r", "--recursive", action="store_true", help="批处理时递归扫描子目录")
    parser.add_argument("-s", "--skip-existing", action="store_true", help="若目标 PDF 已存在且非空，则跳过转换 (断点续转)")
    parser.add_argument("-w", "--workers", type=int, default=1, help="批处理并发线程数 (默认: 1 顺序处理，>1 启用多线程加速)")
    parser.add_argument("--dpi", type=float, default=200.0, help="PDF 渲染分辨率 DPI (默认: 200)")
    parser.add_argument("-p", "--password", help="ZIP 解压密码（可选）")
    parser.add_argument("--pwd-file", help="密码字典文件路径（每行一个密码，优先于内置密码库）")
    parser.add_argument("--no-fit-width", action="store_true", help="禁用统一页宽对齐，严格按各页原生像素/DPI 输出")
    parser.add_argument("--no-prompt", action="store_true", help="密码未命中时禁止交互式询问密码，直接跳过并记录失败")

    args = parser.parse_args()

    targets = scan_book_targets(args.inputs, recursive=args.recursive, batch_mode=args.batch)
    if not targets:
        print("❌ 未在输入路径中找到任何有效的书籍目标 (ZIP / PDG 文件夹 / .pdg 文件)", file=sys.stderr)
        sys.exit(1)

    is_batch = args.batch or len(args.inputs) > 1 or len(targets) > 1

    try:
        if not is_batch:
            target = targets[0]
            converter = PdgConverter(
                target,
                output_path=args.output,
                dpi=args.dpi,
                password=args.password,
                pwd_file=args.pwd_file,
                fit_width=not args.no_fit_width,
                interactive=not args.no_prompt,
            )
            converter.convert()
        else:
            result = batch_convert(
                targets,
                output_dir=args.output,
                dpi=args.dpi,
                password=args.password,
                pwd_file=args.pwd_file,
                fit_width=not args.no_fit_width,
                recursive=args.recursive,
                skip_existing=args.skip_existing,
                workers=max(1, args.workers),
                interactive=(not args.no_prompt) if args.workers <= 1 else False,
            )
            if result.failed:
                sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ 用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 转换失败: {e}", file=sys.stderr)
        sys.exit(1)


__all__ = [
    "PdgConverter",
    "PdgPage",
    "PdgDecoderSession",
    "parse_pdg_bytes",
    "parse_bookinfo",
    "parse_bookcontents",
    "scan_book_targets",
    "resolve_output_path",
    "batch_convert",
    "BatchResult",
    "BatchItemResult",
    "main",
]


if __name__ == "__main__":
    main()
