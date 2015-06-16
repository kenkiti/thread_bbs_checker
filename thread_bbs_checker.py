#! -*- coding: utf-8 -*-
import os, sys, yaml, datetime, time
import httplib, urlparse, re, gzip, StringIO
from urlparse import urljoin

import smtplib
from email.MIMEText import MIMEText
from email.Header import Header
from email.Utils import formatdate

__version__ = "0.3" 
_encoding = "utf-8"

try:
    import Growl
except ImportError:
    _is_growl_installed = False
else:
    _is_growl_installed = True

class BearNotify:
    _g = None
    def __init__(self):
        if _is_growl_installed:
            self._g = Growl.GrowlNotifier(
                applicationName="Palloo", notifications=["stuff"],
                #applicationIcon=Growl.Image.imageWithIconForFile(os.getcwd() + '/Domokun_Online.icns')
                applicationIcon=Growl.Image.imageWithIconForFile(os.getcwd() + '/Polygon_bear')
                #applicationIcon=Growl.Image.imageFromPath(os.getcwd() + '/mac03.gif')
                )
            self._g.register()

    def notify(self, title, message):
        if _is_growl_installed:
            self._g.notify(noteType="stuff", title=title, description=message, sticky=False)
        else:
            print "%s\n%s" % (title, message)

class Logger:
    def _now(self):
        return datetime.datetime.now().strftime("%H:%M:%S")

    def info(self, message):
        m = "[%s] %s" % (self._now(), str(message))
        sys.stdout.write(m + "\n")
        sys.stdout.flush()

class Config:
    Path_to_config = 'config.yaml'

    def load(self):
        return yaml.load(open(self.Path_to_config))
        
    def save(self, dat):
        dat = yaml.dump(dat, default_flow_style=False)
        open(self.path_to_config,'w').write(dat)

class Gmail:
    address = None
    password = None
    
    def send_mail(self, to_addr, subject, body):
        encoding = 'ISO-2022-JP'
        msg = MIMEText(body, 'plain', encoding)
        msg['Subject'] = Header(subject, encoding)
        msg['From'] = self.address
        msg['To'] = to_addr
        msg['Date'] = formatdate()

        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(self.address, self.password)
        s.sendmail(self.address, [to_addr], msg.as_string())
        s.close()

class ThreadBBS:
    Title = None
    Header = {'User-Agent': 'Monazilla/1.00 (Palloo/Dev)',
              'Accept-Encoding': 'gzip'}

    Path = None
    Last_Modified = None
    Range = 0
    Line = 0
    ETag = None
    Live = True

    def _dat2html(self, dat):
        br = re.compile("<br>")
        del_tag = re.compile("<.+?>")
        dat = br.sub('\n', dat)
        dat = del_tag.sub('', dat)
        dat = dat.replace("&amp;","&"); # &
        dat = dat.replace("&lt;","<"); # <
        dat = dat.replace("&gt;",">"); # >
        dat = dat.replace("&nbsp;"," "); # half-width space
        return dat

    def _dat2time(self, filename):
        # UnixDateDelta = 25569
        # posix_timestamp = (int(filename[:-4]) - 9 * 60)/(24*60*60) + UnixDateDelta
        posix_timestamp = int(filename[:-4])
        return datetime.datetime.fromtimestamp(posix_timestamp)#.strftime("%Y/%m/%d %H:%M:%S")

    def _timedelta(self, now, date):
        delta = now - date
        return delta.days + float(delta.seconds) / (24 * 60 * 60)

class Jbbs(ThreadBBS):
    # Dat URL: http://jbbs.livedoor.jp/bbs/rawmode.cgi/(category)/(board_no)/(DAT-ID)/
    # CharCode: EUC-JP
    # LineFormat: Number<>Name<>Mail<>Date(ID)<>Message<>Thread Title(exists in only first line)<>
    def _convert_path_to_dat_from_url(self, url):
        if url.count("rawmode.cgi") > 0: return url
        path = re.compile('http://(?P<host>[^\/]+)/([^\/]+)/([^\/]+)/(?P<category>[^\/]+)/(?P<board>[^\/]+)/(?P<datid>[^\/]+)/')
        m = path.search(url)
        return "http://%s/bbs/rawmode.cgi/%s/%s/%s/" % (
            m.group('host'), m.group('category'), m.group('board'), m.group('datid'))

    def _convert_dat(self, dat):
        dat = unicode(dat, 'euc-jp', 'ignore').encode(_encoding)
        dat = dat.strip("\n").split("\n")[1:]
        ret = []
        for line in dat:
            num, name, mail, date, message, title, null = line.split("<>")
            ret.append({
                'number':int(num), 'name': name,
                'mail': mail, 'date': date, 'message': self._dat2html(message)})
        return  ret

    def _get_title(self, dat):
        dat = unicode(dat, 'euc-jp', 'ignore').encode(_encoding)
        line = dat.strip("\n").split("\n")[0]
        num, name, mail, date, message, title, null = line.split("<>")
        return title

    def _get_last_number(self, dat):
        dat = unicode(dat, 'euc-jp','ignore').encode(_encoding)
        dat = dat.strip("\n").split("\n")
        line = dat[-1:][0]
        num, name, mail, date, message, title, null = line.split("<>")
        return int(num)

    def get(self, data):
        if not self.Path: return None
        url = self._convert_path_to_dat_from_url(self.Path)
        if int(self.Line) > 0:
            url = "%s%s-" % (url, self.Line)
        header = self.Header.copy()

        (scheme, location, objpath, param, query, fid) = \
                 urlparse.urlparse(url, 'http')
        con = httplib.HTTPConnection(location)
        con.request('GET', objpath, data, header)

        response = con.getresponse()
        self.Last_Modified =  response.getheader('Last-Modified', None)
        self.ETag = response.getheader('ETag', None)

        if response.status != 200 and response.status != 206:
            return response.status, None

        dat = response.read()
        if response.getheader('Content-Encoding', None)=='gzip':
            gzfile = StringIO.StringIO(dat)
            gzstream = gzip.GzipFile(fileobj=gzfile)
            dat = gzstream.read()

        if self.Line == 0:
            self.Title = self._get_title(dat)

        last_number = self._get_last_number(dat)
        if last_number > self.Line:
            self.Line = last_number
            if self.Line >= 1000 or response.status == 302 or response.status == 404:
                self.Live = False
            else:
                self.Live = True
            return response.status, self._convert_dat(dat)
        else:
            return 304, None

    def get_power_thread(self, board_url, keyword):
        """ The thread which is include keyword and
        the most power in the bulliten board is returned."""
        # Format of subject.txt: (DAT-ID).cgi,(Title)#(181)
        data = None
        header = self.Header.copy()
        url = urljoin(board_url, "subject.txt")
        if keyword:
            keyword = keyword.encode(_encoding)
        else:
            keyword = ""

        (scheme, location, objpath, param, query, fid) = \
                 urlparse.urlparse(url, 'http')
        con = httplib.HTTPConnection(location)
        con.request('GET', objpath, data, header)
        response = con.getresponse()

        dat = response.read()
        if response.getheader('Content-Encoding', None)=='gzip':
            gzfile = StringIO.StringIO(dat)
            gzstream = gzip.GzipFile(fileobj=gzfile)
            dat = gzstream.read()

        num = re.compile("\((\d+?)\)$")
        key = re.compile(keyword)
        now = datetime.datetime.now()
        power_list = []
        for line in dat.strip("\n").split("\n"):
            line = line.split(",")

            title = unicode(line[1], "euc-jp", "ignore").encode(_encoding)
            count = num.search(title).group(1)
            if int(count) == 1000:
                continue

            if not key.search(title):
                continue

            create_date = self._dat2time(line[0])
            power = float(count) / self._timedelta(now, create_date)
            power_list.append((line, power))

        if not power_list:
            return None

        power_list.sort(lambda x,y: cmp(y[1],x[1]))

        #    http://jbbs.livedoor.jp/game/33247/ , 1190441589.cgi
        # => http://jbbs.livedoor.jp/bbs/read.cgi/game/33247/1190441589/
        path = re.compile('http://(?P<host>[^\/]+)/(?P<category>[^\/]+)/(?P<board>[^\/]+)/')
        m = path.search(board_url)
        return "http://%s/bbs/rawmode.cgi/%s/%s/%s/" % (
            m.group('host'), m.group('category'), m.group('board'), power_list[0][0][0][:-4])

class Nichan(ThreadBBS):
    # Dat URL: http://(host)/(board)/dat/(dat-id).dat
    # Char Code: Shift-jis
    # Line Format: Name<>Mail<>Date、ID<>Message<>Thread Title(exists in only first line.)

    def _convert_path_to_dat_from_url(self, url):
        if url[-3:] == "dat": return url
        path = re.compile('http://(?P<host>[^\/]+)/([^\/]+)/([^\/]+)/(?P<board>[^\/]+)/(?P<thread>[^\/]+)/')
        m = path.search(url)
        return "http://%s/%s/dat/%s.dat" % (
            m.group('host'), m.group('board'), m.group('thread'))

    def _convert_dat(self, dat):
        dat = unicode(dat, 'cp932').encode(_encoding)
        dat = dat.strip("\n").split("\n")
        res = []
        number = self.Line - len(dat)
        for line in dat:
            name, mail, date, message, thread = line.split("<>")
            number += 1
            res.append({
                'number': number, 'name': name,
                'mail': mail, 'date': date, 'message': self._dat2html(message)})
        return res

    def _get_title(self, dat):
        dat = unicode(dat, 'cp932').encode(_encoding)
        line = dat.strip("\n").split("\n")[0]
        name, mail, date, message, title = line.split("<>")
        return title

    def get(self, data):
        """ the DAT file and status code are returned.
        """
        if not self.Path: return None
        url = self._convert_path_to_dat_from_url(self.Path)
        header = self.Header.copy()

        if self.Last_Modified:
            header['If-Modified-Since'] = self.Last_Modified
            header['If-None-Match'] = self.ETag
            header['Range'] = "bytes=%d-" % self.Range
            # If specified 'Range' header exists,
            # remove 'Accept-Encoding: gzip' from header.
            del header['Accept-Encoding']

        (scheme, location, objpath, param, query, fid) = \
                 urlparse.urlparse(url, 'http')
        con = httplib.HTTPConnection(location)
        con.request('GET', objpath, data, header)
        response = con.getresponse()
        self.Last_Modified = response.getheader('Last-Modified', None)
        self.ETag = response.getheader('ETag', None)

        if response.status == 302 or response.status == 404:
            self.Live = False
            return response.status, None
        elif response.status != 200 and response.status != 206:
            return response.status, None
            
        dat = response.read()
        if response.getheader('Content-Encoding', None)=='gzip':
            gzfile = StringIO.StringIO(dat)
            gzstream = gzip.GzipFile(fileobj=gzfile)
            dat = gzstream.read()
        if self.Line == 0:
            self.Title = self._get_title(dat)
        self.Range += len(dat)
        self.Line += dat.count("\n")
        if self.Line >= 1000:
            self.Live = False
        else:
            self.Live = True
            
        return response.status, self._convert_dat(dat)

    def get_power_thread(self, board_url, keyword):
        """ The thread which is include keyword and
        the most power in the bulliten board is returned."""
        data = None
        header = self.Header.copy()
        url = urljoin(board_url, "subject.txt")
        if keyword:
            keyword = keyword.encode(_encoding)
        else:
            keyword = ""

        (scheme, location, objpath, param, query, fid) = \
                 urlparse.urlparse(url, 'http')
        con = httplib.HTTPConnection(location)
        con.request('GET', objpath, data, header)
        response = con.getresponse()

        dat = response.read()
        if response.getheader('Content-Encoding', None)=='gzip':
            gzfile = StringIO.StringIO(dat)
            gzstream = gzip.GzipFile(fileobj=gzfile)
            dat = gzstream.read()

        num = re.compile("\((\d+?)\)$")
        key = re.compile(keyword)
        now = datetime.datetime.now()
        power_list = []
        for line in dat.strip("\n").split("\n"):
            line = line.split("<>")

            title = unicode(line[1], "cp932", "ignore").encode(_encoding)
            count = num.search(title).group(1)
            if int(count) == 1001:
                continue

            if not key.search(title):
                continue

            create_date = self._dat2time(line[0])
            power = float(count) / self._timedelta(now, create_date)
            power_list.append((line, power))

        if not power_list:
            return None

        power_list.sort(lambda x,y: cmp(y[1],x[1]))
        return urljoin(board_url, "dat/%s" % power_list[0][0][0])

def AA_check(message):
    ## AA Check
    counter = 0
    aas = [":", ";", ".", "?", "&", "━", "┃", "(", ")", "／", "ノ", "＼", "|","ヽ","─"]
    for aa in aas:
        counter += message.count(aa)
    if counter > 25: message = "AA略"
    return message

def distinguish_bbs(path, last_modified=None, dat_range=0, line=0, live=True, etag=None):
    search_2ch = re.compile('2ch\.net')
    search_jbbs = re.compile('jbbs\.livedoor\.jp')
    search_yykakiko = re.compile('yy\d+\.\d+\.kg')

    if search_2ch.search(path):
        bbs = Nichan()
    elif search_jbbs.search(path):
        bbs = Jbbs()
    elif search_yykakiko.search(path):
        bbs = Nichan()
    else:
        raise

    return bbs

def visit_thread(t):
    status_message = {
        200:'スレ取得',
        206:'差分取得',
        302:'DAT落ち',
        304:'更新なし',
        404:'ファイルがないよ',
        416:'なんかエラーだって',
        }
    logger = Logger()
    
    flg_init_thread = False
    flg_get_dat = False
    message = ""

    bbs = distinguish_bbs(t['Path'])
    bbs.Path = t['Path']
    bbs.Live = t['Live']
    bbs.ETag = t['ETag']
    bbs.Last_Modified = t['Last-Modified']
    bbs.Range = t['Range']
    bbs.Line = t['Line']

    status, dat = bbs.get(None)
    if bbs.Title:
        flg_init_thread = True
        t['Title'] = bbs.Title

    if status == 200 or status == 206:
        flg_get_dat = True
        t['Last-Modified'] = bbs.Last_Modified
        t['ETag'] = bbs.ETag
        t['Range'] = bbs.Range
        t['Line'] = bbs.Line
    t['Live'] = bbs.Live

    # If Http Error '416 Requested Range Not Satisfiable' is happend,
    # obtain thread data again.
    if status == 416:
        t['Last-Modified'] = None
        t['ETag'] = None
        t['Range'] = 0
        t['Line'] = 0

    logger.info("%s(%d):%s" % (status_message[status], t['Line'],  t['Title']))
    if flg_init_thread == True or flg_get_dat == False:
        return ""

    # Composes a message from data.
    if t['Name']:
        name = re.compile(t['Name'])
        for d in dat:
            if not name.search(d['name']):
                continue
            message += text_wrapper(d['number'], AA_check(d['message']))
    else:
        for d in dat:
            message += text_wrapper(d['number'], AA_check(d['message']))
    logger.info('最終書込:%s レス取得数:%d' % (dat[-1]['date'], len(dat)))
    if message == "": return ""

    return message

def text_wrapper(number, message):
#     import textwrap
#     wrapper = textwrap.TextWrapper(initial_indent="%4d " % number, subsequent_indent=" "*7, width=30)
#     return wrapper.fill(unicode(message,"utf-8")) + "\n"
    return "\n%d %s" % (number, message)

def send_mail(title, message):
    config = Config().load()
    logger = Logger()

    mail = Gmail()
    mail.address = config['gmail_address']
    mail.password = config['password']
    subject = u'新着レスがあります'.encode('ISO-2022-JP', 'ignore')
    message = unicode(message, _encoding).encode('ISO-2022-JP', 'ignore')
    try:
        mail.send_mail(config['to_address'], subject, message)
    except:
        logger.info("メール送信に失敗しました。(%s)" % str(sys.exc_info()[0]))
    else:
        logger.info("メールを送信しました。")

def run():
    def get_value(c, key):
        if c.has_key(key):
            return c[key]
        else:
            return None

    # initialize
    config = Config().load()
    logger = Logger()
    boards, threads = [], []

    if config.has_key('thread'):
        for c in config['thread']:
            threads.append({
                'Path': c['path'],
                'Name': get_value(c, 'name'),
                'Title': None,
                'Last-Modified': None,
                'Line': 0, 'Range': 0, 'ETag': None, 'Live': True,
                })

    if config.has_key('board'):
        for c in config['board']:
            boards.append({
                'Board': get_value(c,'board'),
                'Thread': get_value(c,'thread'),
                'Path': None,
                'Name': get_value(c, 'name'),
                'Title': None,
                'Last-Modified': None,
                'Line': 0, 'Range': 0, 'ETag': None, 'Live': False,
                })

    # main routine
    notify = get_value(config,'notify')
    bn = BearNotify()
    
    while True:
        messages = ""
        for t in threads:
            if not t['Live']:
                continue
            
            message = visit_thread(t)
            if message:
                message_mail = "-------------------\n%s\n-------------------\n%s" % (t['Title'], message)
            else:
                continue
                
            if _is_growl_installed and notify == 'growl':
                bn.notify(t['Title'], message)
            elif notify == 'mail':
                messages += message_mail
            else:
                print message_mail

        messages = ""
        for b in boards:
            if not b['Live']:
                bbs = distinguish_bbs(b['Board'])
                dat_file = bbs.get_power_thread(b['Board'], b['Thread'])
                if dat_file:
                    logger.info("%sから最も勢いのあるスレッドを取得" % b['Board'])
                    b['Path'] = dat_file
                    b['Last-Modified'] = None
                    b['ETag'] = None
                    b['Range'] = 0
                    b['Line'] = 0
                    b['Live'] = True
                else:
                    continue
                    
            message = visit_thread(b)
            if message:
                message_mail = "-------------------\n%s\n-------------------\n%s" % (b['Title'], message)
            else:
                continue

            if _is_growl_installed and notify == 'growl':
                bn.notify(b['Title'], message)
            elif notify == 'mail':
                messages += message_mail
            else:
                print message_mail

        # The message is sent with mail.
        if messages and notify == 'Mail':
            send_mail(messages)
                    
        logger.info("%d秒待機" % config['wait'])
        time.sleep(config['wait'])

if __name__ == '__main__':
    run()


