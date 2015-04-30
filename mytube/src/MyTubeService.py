# -*- coding: iso-8859-1 -*-
from enigma import ePythonMessagePump

from __init__ import decrypt_block
from ThreadQueue import ThreadQueue
import gdata.youtube
import gdata.youtube.service
from gdata.service import BadAuthentication

from apiclient.discovery import build
from apiclient.errors import HttpError
import datetime
import re

from twisted.web import client
from twisted.internet import reactor
from urllib2 import Request, URLError, urlopen as urlopen2
from socket import gaierror, error
import os, socket, httplib
from urllib import quote, unquote_plus, unquote, urlencode
from httplib import HTTPConnection, CannotSendRequest, BadStatusLine, HTTPException

from urlparse import parse_qs, parse_qsl
from threading import Thread

HTTPConnection.debuglevel = 1

DEVELOPER_KEY = "AIzaSyChvLZRinP2xwXoXWNEqVeaz71SQJnjrlc"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

if 'HTTPSConnection' not in dir(httplib):
	# python on enimga2 has no https socket support
	gdata.youtube.service.YOUTUBE_USER_FEED_URI = 'http://gdata.youtube.com/feeds/api/users'

def validate_cert(cert, key):
	buf = decrypt_block(cert[8:], key)
	if buf is None:
		return None
	return buf[36:107] + cert[139:196]

def get_rnd():
	try:
		rnd = os.urandom(8)
		return rnd
	except:
		return None

std_headers = {
	'User-Agent': 'Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.2.6) Gecko/20100627 Firefox/3.6.6',
	'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
	'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
	'Accept-Language': 'en-us,en;q=0.5',
}

#config.plugins.mytube = ConfigSubsection()
#config.plugins.mytube.general = ConfigSubsection()
#config.plugins.mytube.general.useHTTPProxy = ConfigYesNo(default = False)
#config.plugins.mytube.general.ProxyIP = ConfigIP(default=[0,0,0,0])
#config.plugins.mytube.general.ProxyPort = ConfigNumber(default=8080)
#class MyOpener(FancyURLopener):
#	version = 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.8.0.12) Gecko/20070731 Ubuntu/dapper-security Firefox/1.5.0.12'


class GoogleSuggestions():
	def __init__(self):
		self.hl = "en"
		self.conn = None

	def prepareQuery(self):
		#GET /complete/search?output=toolbar&client=youtube-psuggest&xml=true&ds=yt&hl=en&jsonp=self.gotSuggestions&q=s
		self.prepQuerry = "/complete/search?output=toolbar&client=youtube&xml=true&ds=yt&"
		if self.hl is not None:
			self.prepQuerry = self.prepQuerry + "hl=" + self.hl + "&"
		self.prepQuerry = self.prepQuerry + "jsonp=self.gotSuggestions&q="
		print "[MyTube - GoogleSuggestions] prepareQuery:",self.prepQuerry

	def getSuggestions(self, queryString):
		self.prepareQuery()
		if queryString is not "":
			query = self.prepQuerry + quote(queryString)
			self.conn = HTTPConnection("google.com")
			try:
				self.conn = HTTPConnection("google.com")
				self.conn.request("GET", query, "", {"Accept-Encoding": "UTF-8"})
			except (CannotSendRequest, gaierror, error):
				self.conn.close()
				print "[MyTube - GoogleSuggestions] Can not send request for suggestions"
				return None
			else:
				try:
					response = self.conn.getresponse()
				except BadStatusLine:
					self.conn.close()
					print "[MyTube - GoogleSuggestions] Can not get a response from google"
					return None
				else:
					if response.status == 200:
						data = response.read()
						header = response.getheader("Content-Type", "text/xml; charset=ISO-8859-1")
						charset = "ISO-8859-1"
						try:
							charset = header.split(";")[1].split("=")[1]
							print "[MyTube - GoogleSuggestions] Got charset %s" %charset
						except:
							print "[MyTube - GoogleSuggestions] No charset in Header, falling back to %s" %charset
						data = data.decode(charset).encode("utf-8")
						self.conn.close()
						return data
					else:
						self.conn.close()
						return None
		else:
			return None

class MyTubeFeedEntry():
	def __init__(self, feed, entry, favoritesFeed = False):
		self.feed = feed
		self.entry = entry
		self.favoritesFeed = favoritesFeed
		self.thumbnail = {}
		"""self.myopener = MyOpener()
		urllib.urlopen = MyOpener().open
		if config.plugins.mytube.general.useHTTPProxy.value is True:
			proxy = {'http': 'http://'+str(config.plugins.mytube.general.ProxyIP.getText())+':'+str(config.plugins.mytube.general.ProxyPort.value)}
			self.myopener = MyOpener(proxies=proxy)
			urllib.urlopen = MyOpener(proxies=proxy).open
		else:
			self.myopener = MyOpener()
			urllib.urlopen = MyOpener().open"""

	def isPlaylistEntry(self):
		return False

	def getTubeId(self):
		#print "[MyTubeFeedEntry] getTubeId"
		try:
			return str(self.entry["id"])
		except KeyError:
			return None

	def getTitle(self):
		#print "[MyTubeFeedEntry] getTitle",self.entry.media.title.text
		try:
			return self.entry["snippet"]["title"].encode('utf-8').strip()
		except KeyError:
			return None

	def getDescription(self):
		try:
			return self.entry["snippet"]["description"].encode('utf-8').strip()
		except KeyError:
			return None

	def getThumbnailUrl(self, index=0):
		#print "[MyTubeFeedEntry] getThumbnailUrl"
		try:
			return str(self.entry["snippet"]["thumbnails"]["default"]["url"])
		except KeyError:
			return None

	def getPublishedDate(self):
		try:
			return str(self.entry["snippet"]["publishedAt"])
		except KeyError:
			return None

	def getViews(self):
		try:
			return int(self.entry["statistics"]["viewCount"])
		except KeyError:
			return None
		except ValueError:
			return None

	def parse_duration(self, duration):
		# isodate replacement


		if 'P' in duration:
			dt, duration = duration.split('P')

		duration_regex = re.compile(
			r'^((?P<years>\d+)Y)?'
			r'((?P<months>\d+)M)?'
			r'((?P<weeks>\d+)W)?'
			r'((?P<days>\d+)D)?'
			r'(T'
			r'((?P<hours>\d+)H)?'
			r'((?P<minutes>\d+)M)?'
			r'((?P<seconds>\d+)S)?'
			r')?$'
		)

		data = duration_regex.match(duration)
		if not data or duration[-1] == 'T':
			raise ValueError("'P%s' does not match ISO8601 format" % duration)
		data = {k:int(v) for k,v in data.groupdict().items() if v}
		if 'years' in data or 'months' in data:
			raise ValueError('Year and month values are not supported in python timedelta')

		return datetime.timedelta(**data)

	def getDuration(self):
		try:
			return self.parse_duration(str(self.entry["contentDetails"]["duration"])).total_seconds()
		except KeyError, e:
			print e
			return 0
		except ValueError, e:
			print e
			return 0

	def getRatingAverage(self):
		# @TODO
		return 0


	def getNumRaters(self):
		try:
			return int(self.entry["statistics"]["likeCount"]) + int(self.entry["statistics"]["dislikeCount"])
		except KeyError:
			return None
		except ValueError:
			return None

	def getAuthor(self):
		return self.getChannelTitle()

	def getChannelTitle(self):
		try:
			return str(self.entry["snippet"]["channelTitle"].encode('utf-8').strip())
		except KeyError:
			return None

	def getChannelId(self):
		try:
			return str(self.entry["snippet"]["channelId"].encode('utf-8').strip())
		except KeyError:
			return None

	def getUserFeedsUrl(self):
		return None

	def getUserId(self):
		try:
			return self.entry["snippet"]["channelTitle"].encode('utf-8').strip()
		except KeyError:
			return None

	def subscribeToUser(self):
		return myTubeService.SubscribeToUser(self.getUserId())

	def addToFavorites(self):
		return myTubeService.addToFavorites(self.getTubeId())

	def PrintEntryDetails(self):
		EntryDetails = { 'Title': None, 'TubeID': None, 'Published': None, 'Published': None, 'Description': None, 'Category': None, 'Tags': None, 'Duration': None, 'Views': None, 'Rating': None, 'Thumbnails': None}
		EntryDetails['Title'] = self.getTitle()
		EntryDetails['TubeID'] = self.getTubeId()
		EntryDetails['Description'] = self.getDescription()
		EntryDetails['Category'] = None #self.entry.media.category[0].text
		EntryDetails['Tags'] = None #self.entry.media.keywords.text
		EntryDetails['Published'] = self.getPublishedDate()
		EntryDetails['Views'] = self.getViews()
		EntryDetails['Duration'] = self.getDuration()
		EntryDetails['Rating'] = self.getNumRaters()
		EntryDetails['RatingAverage'] = self.getRatingAverage()
		EntryDetails['Author'] = self.getAuthor()
		# show thumbnails
		list = []

		if self.getThumbnailUrl() is not None:
			list.append(self.getThumbnailUrl())
			print 'Thumbnail url: %s' % self.getThumbnailUrl()

		EntryDetails['Thumbnails'] = list
		return EntryDetails

	def getVideoUrl(self):
		VIDEO_FMT_PRIORITY_MAP = {
			'38' : 1, #MP4 Original (HD)
			'37' : 2, #MP4 1080p (HD)
			'22' : 3, #MP4 720p (HD)
			'18' : 4, #MP4 360p
			'35' : 5, #FLV 480p
			'34' : 6, #FLV 360p
		}
		video_url = None
		video_id = str(self.getTubeId())

		# Getting video webpage
		#URLs for YouTube video pages will change from the format http://www.youtube.com/watch?v=ylLzyHk54Z0 to http://www.youtube.com/watch#!v=ylLzyHk54Z0.
		watch_url = 'http://www.youtube.com/watch?v=%s&gl=US&hl=en' % video_id
		watchrequest = Request(watch_url, None, std_headers)
		try:
			print "[MyTube] trying to find out if a HD Stream is available",watch_url
			watchvideopage = urlopen2(watchrequest).read()
		except (URLError, HTTPException, socket.error), err:
			print "[MyTube] Error: Unable to retrieve watchpage - Error code: ", str(err)
			return video_url

		# Get video info
		for el in ['&el=embedded', '&el=detailpage', '&el=vevo', '']:
			info_url = ('http://www.youtube.com/get_video_info?&video_id=%s%s&ps=default&eurl=&gl=US&hl=en' % (video_id, el))
			request = Request(info_url, None, std_headers)
			try:
				infopage = urlopen2(request).read()
				videoinfo = parse_qs(infopage)
				if ('url_encoded_fmt_stream_map' or 'fmt_url_map') in videoinfo:
					break
			except (URLError, HTTPException, socket.error), err:
				print "[MyTube] Error: unable to download video infopage",str(err)
				return video_url

		if ('url_encoded_fmt_stream_map' or 'fmt_url_map') not in videoinfo:
			# Attempt to see if YouTube has issued an error message
			if 'reason' not in videoinfo:
				print '[MyTube] Error: unable to extract "fmt_url_map" or "url_encoded_fmt_stream_map" parameter for unknown reason'
			else:
				reason = unquote_plus(videoinfo['reason'][0])
				print '[MyTube] Error: YouTube said: %s' % reason.decode('utf-8')
			return video_url

		video_fmt_map = {}
		fmt_infomap = {}
		if videoinfo.has_key('url_encoded_fmt_stream_map'):
			tmp_fmtUrlDATA = videoinfo['url_encoded_fmt_stream_map'][0].split(',')
		else:
			tmp_fmtUrlDATA = videoinfo['fmt_url_map'][0].split(',')
		for fmtstring in tmp_fmtUrlDATA:
			fmturl = fmtid = fmtsig = ""
			if videoinfo.has_key('url_encoded_fmt_stream_map'):
				try:
					for arg in fmtstring.split('&'):
						if arg.find('=') >= 0:
							print arg.split('=')
							key, value = arg.split('=')
							if key == 'itag':
								if len(value) > 3:
									value = value[:2]
								fmtid = value
							elif key == 'url':
								fmturl = value
							elif key == 'sig':
								fmtsig = value
								
					if fmtid != "" and fmturl != "" and fmtsig != ""  and VIDEO_FMT_PRIORITY_MAP.has_key(fmtid):
						video_fmt_map[VIDEO_FMT_PRIORITY_MAP[fmtid]] = { 'fmtid': fmtid, 'fmturl': unquote_plus(fmturl), 'fmtsig': fmtsig }
						fmt_infomap[int(fmtid)] = "%s&signature=%s" %(unquote_plus(fmturl), fmtsig)
					fmturl = fmtid = fmtsig = ""

				except:
					print "error parsing fmtstring:",fmtstring
					
			else:
				(fmtid,fmturl) = fmtstring.split('|')
			if VIDEO_FMT_PRIORITY_MAP.has_key(fmtid) and fmtid != "":
				video_fmt_map[VIDEO_FMT_PRIORITY_MAP[fmtid]] = { 'fmtid': fmtid, 'fmturl': unquote_plus(fmturl) }
				fmt_infomap[int(fmtid)] = unquote_plus(fmturl)
		print "[MyTube] got",sorted(fmt_infomap.iterkeys())
		if video_fmt_map and len(video_fmt_map):
			print "[MyTube] found best available video format:",video_fmt_map[sorted(video_fmt_map.iterkeys())[0]]['fmtid']
			best_video = video_fmt_map[sorted(video_fmt_map.iterkeys())[0]]
			video_url = "%s&signature=%s" %(best_video['fmturl'].split(';')[0], best_video['fmtsig'])
			print "[MyTube] found best available video url:",video_url

		return video_url

	def getResponseVideos(self):
		print "[MyTubeFeedEntry] getResponseVideos()"
		for link in self.entry.link:
			#print "Responses link: ", link.rel.endswith
			if link.rel.endswith("video.responses"):
				print "Found Responses: ", link.href
				return link.href

	def getUserVideos(self):
		print "[MyTubeFeedEntry] getUserVideos()"
		username = self.getUserId()
		myuri = 'http://gdata.youtube.com/feeds/api/users/%s/uploads' % username
		print "Found Uservideos: ", myuri
		return myuri

class MyTubePlayerService():
#	Do not change the client_id and developer_key in the login-section!
#	ClientId: ytapi-dream-MyTubePlayer-i0kqrebg-0
#	DeveloperKey: AI39si4AjyvU8GoJGncYzmqMCwelUnqjEMWTFCcUtK-VUzvWygvwPO-sadNwW5tNj9DDCHju3nnJEPvFy4WZZ6hzFYCx8rJ6Mw

	cached_auth_request = {}
	current_auth_token = None
	yt_service = None
	currentPage = 1

	def __init__(self):
		print "[MyTube] MyTubePlayerService - init"
		self.feedentries = []
		self.lastList = {}
		self.lastEndpoint = None
		self.feed = None

	def startService(self):
		print "[MyTube] MyTubePlayerService - startService"

		self.yt_service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=DEVELOPER_KEY)

		# missing ssl support? youtube will help us on some feed urls
		#self.yt_service.ssl = self.supportsSSL()

		# dont use it on class init; error on post and auth
		#self.yt_service.developer_key = 'AI39si4AjyvU8GoJGncYzmqMCwelUnqjEMWTFCcUtK-VUzvWygvwPO-sadNwW5tNj9DDCHju3nnJEPvFy4WZZ6hzFYCx8rJ6Mw'
		#self.yt_service.client_id = 'ytapi-dream-MyTubePlayer-i0kqrebg-0'

		# yt_service is reinit on every feed build; cache here to not reauth. remove init every time?
		if self.current_auth_token is not None:
			print "[MyTube] MyTubePlayerService - auth_cached"
			#self.yt_service.SetClientLoginToken(self.current_auth_token)
		
#		self.loggedIn = False
		#os.environ['http_proxy'] = 'http://169.229.50.12:3128'
		#proxy = os.environ.get('http_proxy')
		#print "FOUND ENV PROXY-->",proxy
		#for a in os.environ.keys():
		#	print a

	def stopService(self):
		print "[MyTube] MyTubePlayerService - stopService"
		del self.ytService

	def getLoginTokenOnCurl(self, email, pw):
		return None

		opts = {
		  'service':'youtube',
		  'accountType': 'HOSTED_OR_GOOGLE',
		  'Email': email,
		  'Passwd': pw,
		  'source': self.yt_service.client_id,
		}
		
		print "[MyTube] MyTubePlayerService - Starting external curl auth request"
		result = os.popen('curl -s -k -X POST "%s" -d "%s"' % (gdata.youtube.service.YOUTUBE_CLIENTLOGIN_AUTHENTICATION_URL , urlencode(opts))).read()
		
		return result

	def supportsSSL(self):
		return 'HTTPSConnection' in dir(httplib)

	def getFormattedTokenRequest(self, email, pw):
		return dict(parse_qsl(self.getLoginTokenOnCurl(email, pw).strip().replace('\n', '&')))
	
	def getAuthedUsername(self):
		# on external curl we can get real username
		if self.cached_auth_request.get('YouTubeUser') is not None:
			return self.cached_auth_request.get('YouTubeUser')

		if self.is_auth() is False:
			return ''

		# current gdata auth class save doesnt save realuser
		return 'Logged In'

	def auth_user(self, username, password):
		print "[MyTube] MyTubePlayerService - auth_use - " + str(username)

		if self.yt_service is None:
			self.startService()
		
		if self.current_auth_token is not None:
			print "[MyTube] MyTubePlayerService - auth_cached"
			self.yt_service.SetClientLoginToken(self.current_auth_token)
			return

		if self.supportsSSL() is False:
			print "[MyTube] MyTubePlayerService - HTTPSConnection not found trying external curl"
			self.cached_auth_request = self.getFormattedTokenRequest(username, password)
			if self.cached_auth_request.get('Auth') is None:
				raise Exception('Got no auth token from curl; you need curl and valid youtube login data')
			
			self.yt_service.SetClientLoginToken(self.cached_auth_request.get('Auth'))
		else:
			print "[MyTube] MyTubePlayerService - Using regularly ProgrammaticLogin for login"
			self.yt_service.email = username
			self.yt_service.password  = password
			self.yt_service.ProgrammaticLogin()
			
		# double check login: reset any token on wrong logins
		if self.is_auth() is False:
			print "[MyTube] MyTubePlayerService - auth_use - auth not possible resetting"
			self.resetAuthState()
			return

		print "[MyTube] MyTubePlayerService - Got successful login"
		self.current_auth_token = self.auth_token()

	def resetAuthState(self):
		print "[MyTube] MyTubePlayerService - resetting auth"
		self.cached_auth_request = {}
		self.current_auth_token = None

		if self.yt_service is None:
			return

		self.yt_service.current_token = None
		self.yt_service.token_store.remove_all_tokens()

	def is_auth(self):
		return False
		if self.current_auth_token is not None:
			return True		
		
		if self.yt_service.current_token is None:
			return False
		
		return self.yt_service.current_token.get_token_string() != 'None'

	def auth_token(self):
		return self.yt_service.current_token.get_token_string()

	def getFeedService(self, feedname):
		if feedname == "top_rated":
			return self.yt_service.GetTopRatedVideoFeed
		elif feedname == "most_viewed":
			return self.yt_service.GetMostViewedVideoFeed
		elif feedname == "recently_featured":
			return self.yt_service.GetRecentlyFeaturedVideoFeed
		elif feedname == "top_favorites":
			return self.yt_service.GetTopFavoritesVideoFeed
		elif feedname == "most_recent":
			return self.yt_service.GetMostRecentVideoFeed
		elif feedname == "most_discussed":
			return self.yt_service.GetMostDiscussedVideoFeed
		elif feedname == "most_linked":
			return self.yt_service.GetMostLinkedVideoFeed
		elif feedname == "most_responded":
			return self.yt_service.GetMostRespondedVideoFeed
		return self.yt_service.GetYouTubeVideoFeed

	def getFeed(self, url, feedname = "", callback = None, errorback = None):
		print "[MyTube] MyTubePlayerService - getFeed:",url, feedname
		self.feedentries = []

		if feedname == "my_subscriptions":
			url = "http://gdata.youtube.com/feeds/api/users/default/newsubscriptionvideos"
		elif feedname == "my_favorites":
			url = "http://gdata.youtube.com/feeds/api/users/default/favorites"
		elif feedname == "my_history":
			url = "http://gdata.youtube.com/feeds/api/users/default/watch_history?v=2"
		elif feedname == "my_recommendations":
			url = "http://gdata.youtube.com/feeds/api/users/default/recommendations?v=2"
		elif feedname == "my_watch_later":
			url = "http://gdata.youtube.com/feeds/api/users/default/watch_later?v=2"
		elif feedname == "my_uploads":
			url = "http://gdata.youtube.com/feeds/api/users/default/uploads"
		elif feedname in ("hd", "most_popular", "most_shared", "on_the_web"):
			if feedname == "hd":
				url = "http://gdata.youtube.com/feeds/api/videos/-/HD"
			else:
				url = url + feedname
		elif feedname in ("top_rated","most_viewed","recently_featured","top_favorites","most_recent","most_discussed","most_linked","most_responded"):
			pass

		return self.search(searchTerms="test", callback=callback, errorback=errorback)

	def search(self, searchTerms, startIndex = 1, maxResults = 25,
					orderby = "relevance", time = 'all_time', racy = "include",
					author = "", lr = "", categories = "", sortOrder = "ascending",
					callback = None, errorback = None, pageToken = None):
		print "[MyTube] MyTubePlayerService - search()"
		self.feedentries = []

		publishedAfterDate = None
		if time == "today":
			publishedAfterDate = datetime.datetime.today()
		elif time == "this_week":
			publishedAfterDate = datetime.datetime.today() - datetime.timedelta(weeks=1)
		elif time == "last_month":
			publishedAfterDate = datetime.datetime.today() - datetime.timedelta(weeks=4)

		publishedAfter = None
		if publishedAfterDate is not None:
			publishedAfter = publishedAfterDate.replace(hour=0, minute=0, second=0, microsecond=0).utcnow().isoformat("T") + "Z"

		if orderby == "published":
			orderby = "date"

		return self.searchArgs({
			"maxResults": maxResults,
			"order": orderby,
			"q": searchTerms,
			"publishedAfter": publishedAfter,
			"pageToken": pageToken,
		}, callback, errorback)

	def searchArgs(self, args, callback = None, errorback = None, endpoint = "search"):
		print "[MyTube] MyTubePlayerService - searchArgs()"
		self.feedentries = []
		self.currentPage = 1

		if 'type' not in args:
			args["type"] = "video"

		if 'maxResults' not in args:
			args["maxResults"] = 25

		self.lastList = args
		self.lastEndpoint = endpoint

		queryThread = YoutubeQueryThread(getattr(self.yt_service, endpoint)(), args, self.gotFeed, self.gotFeedError, callback, errorback, self.yt_service)
		queryThread.start()

		return queryThread

	def getChannelPlaylistId(self, channelId):

		response = myTubeService.yt_service.channels().list(
			id=channelId,
			part="contentDetails"
		).execute()

		items = response.get("items", [])
		if len(items) == 0:
			return

		try:
			return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
		except KeyError:
			return 0


	def getNextPage(self, pageToken, callback = None, errorback = None):
		print "[MyTube] MyTubePlayerService - getNextPage:",pageToken
		self.feedentries = []

		args = self.lastList
		args["pageToken"] = pageToken
		if 'maxResults' not in args:
			del args["maxResults"]

		print "next page" + pageToken

		queryThread = YoutubeQueryThread(getattr(self.yt_service, self.lastEndpoint)(), args, self.gotFeed, self.gotFeedError, callback, errorback, self.yt_service)
		queryThread.start()

		self.currentPage += 1

		return queryThread

	def gotFeed(self, feed, callback):
		if feed is not None:
			self.feed = feed
			for entry in self.feed['items']:
				MyFeedEntry = MyTubeFeedEntry(self, entry)
				self.feedentries.append(MyFeedEntry)
		if callback is not None:
			callback(self.feed)

	def gotFeedError(self, exception, errorback = None):
		if errorback is not None:
			errorback(exception)

	def SubscribeToUser(self, username):
		try:
			new_subscription = self.yt_service.AddSubscriptionToChannel(username_to_subscribe_to=username)
	
			if isinstance(new_subscription, gdata.youtube.YouTubeSubscriptionEntry):
				print '[MyTube] MyTubePlayerService: New subscription added'
				return _('New subscription added')
			
			return _('Unknown error')
		except gdata.service.RequestError as req:
			return str('Error: ' + str(req[0]["body"]))
		except Exception as e:
			return str('Error: ' + e)
	
	def addToFavorites(self, video_id):
		try:
			video_entry = self.yt_service.GetYouTubeVideoEntry(video_id=video_id)
			response = self.yt_service.AddVideoEntryToFavorites(video_entry)
			
			# The response, if succesfully posted is a YouTubeVideoEntry
			if isinstance(response, gdata.youtube.YouTubeVideoEntry):
				print '[MyTube] MyTubePlayerService: Video successfully added to favorites'
				return _('Video successfully added to favorites')	
	
			return _('Unknown error')
		except gdata.service.RequestError as req:
			return str('Error: ' + str(req[0]["body"]))
		except Exception as e:
			return str('Error: ' + e)
	
	def getTitle(self):
		return ""

	def getEntries(self):
		return self.feedentries

	def itemCount(self):
		return ""

	def getTotalResults(self):
		if self.feed["pageInfo"]["totalResults"] is None:
			return 0

		return self.feed["pageInfo"]["totalResults"]

	def getNextFeedEntriesURL(self):
		try:
			return self.feed["nextPageToken"]
		except KeyError:
			print "error in getNextFeedEntriesURL"
			return None

	def getCurrentPage(self):
		return self.currentPage

class YoutubeQueryThread(Thread):
	def __init__(self, youtube_endpoint, args, gotFeed, gotFeedError, callback, errorback, youtube):
		Thread.__init__(self)
		self.messagePump = ePythonMessagePump()
		self.messages = ThreadQueue()
		self.gotFeed = gotFeed
		self.gotFeedError = gotFeedError
		self.callback = callback
		self.errorback = errorback
		self.youtube_endpoint = youtube_endpoint
		self.youtube = youtube
		self.args = args
		self.canceled = False
		#self.messagepPump_conn = self.messagePump.recv_msg.connect(self.finished)
		self.messagePump.recv_msg.get().append(self.finished)

	def cancel(self):
		self.canceled = True

	def run(self):

		try:

			args = self.args
			args['part'] = "id"
			search_response = self.youtube_endpoint.list(**args).execute()

			search_videos = []

			for search_result in search_response.get("items", []):
				search_videos.append(search_result["id"]["videoId"])

			if len(search_videos) == 0:
				self.messages.push((False, "nothing found", self.errorback))
				self.messagePump.send(0)
				return

			video_response = self.youtube.videos().list(
				id=",".join(search_videos),
				part='id,snippet,recordingDetails,statistics,contentDetails'
			).execute()

			search_response["items"] = video_response.get("items", [])

			self.messages.push((True, search_response, self.callback))
			self.messagePump.send(0)
		except Exception, ex:
			print ex
			self.messages.push((False, ex, self.errorback))
			self.messagePump.send(0)

	def finished(self, val):
		if not self.canceled:
			message = self.messages.pop()
			if message[0]:
				self.gotFeed(message[1], message[2])
			else:
				self.gotFeedError(message[1], message[2])

myTubeService = MyTubePlayerService()

