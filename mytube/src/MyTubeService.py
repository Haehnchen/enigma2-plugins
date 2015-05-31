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

from oauth2client.client import OAuth2Credentials
import YoutubeRequests
import json

import httplib2

HTTPConnection.debuglevel = 1

DEVELOPER_KEY = "AIzaSyChvLZRinP2xwXoXWNEqVeaz71SQJnjrlc"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

YOUTUBE_API_CLIENT_ID = "1052746365248-me8avpg36emif15efi4fe1or4ngr30nt.apps.googleusercontent.com"
YOUTUBE_API_CLIENT_SECRET = "kF_zGCwwBXr1VROqTFaQoHJZ"
YOUTUBE_API_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_API_CLIENT_TOKEN_REFRESH = "https://accounts.google.com/o/oauth2/token"

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
		return myTubeService.SubscribeToUser(self.getChannelId())

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
	yt_service = None
	currentPage = 1
	http_credentials = None
	is_authenticated = False
	channel_playlists = None
	refresh_token = None

	def __init__(self):
		print "[MyTube] MyTubePlayerService - init"
		self.feedentries = []
		self.lastRequest = None
		self.feed = None

	def startService(self):
		print "[MyTube] MyTubePlayerService - startService"

		if self.refresh_token is None:
			self.yt_service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=DEVELOPER_KEY)
			return

		if self.http_credentials is None:
			print "[MyTube] MyTubePlayerService - build getCredentials with " + self.refresh_token
			try:

				self.http_credentials = OAuth2Credentials(
					access_token=None,
					client_id=YOUTUBE_API_CLIENT_ID,
					client_secret=YOUTUBE_API_CLIENT_SECRET,
					refresh_token=self.refresh_token,
					token_expiry=None,
					token_uri=YOUTUBE_API_CLIENT_TOKEN_REFRESH,
					user_agent=None
				).authorize(httplib2.Http())

				self.yt_service = build(
					YOUTUBE_API_SERVICE_NAME,
					YOUTUBE_API_VERSION,
					developerKey=DEVELOPER_KEY,
					http=self.http_credentials
				)

				self.is_authenticated = True

			except Exception, e:
				print "[MyTube] MyTubePlayerService - getCredentials error " + str(e)
				self.is_authenticated = False
				self.refresh_token = None
				self.yt_service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=DEVELOPER_KEY)

		# missing ssl support? youtube will help us on some feed urls
		#self.yt_service.ssl = self.supportsSSL()

		# dont use it on class init; error on post and auth
		#self.yt_service.developer_key = 'AI39si4AjyvU8GoJGncYzmqMCwelUnqjEMWTFCcUtK-VUzvWygvwPO-sadNwW5tNj9DDCHju3nnJEPvFy4WZZ6hzFYCx8rJ6Mw'
		#self.yt_service.client_id = 'ytapi-dream-MyTubePlayer-i0kqrebg-0'

#		self.loggedIn = False
		#os.environ['http_proxy'] = 'http://169.229.50.12:3128'
		#proxy = os.environ.get('http_proxy')
		#print "FOUND ENV PROXY-->",proxy
		#for a in os.environ.keys():
		#	print a

	def stopService(self):
		print "[MyTube] MyTubePlayerService - stopService"
		del self.refresh_token
		del self.http_credentials
		del self.yt_service

	def getAuthedUsername(self):
		if self.is_auth() is False:
			return ''

		# current gdata auth class save doesnt save realuser
		return 'Logged In'

	def restartWithToken(self, reset_token):
		print "[MyTube] MyTubePlayerService - auth_use - " + str(reset_token)
		self.refresh_token = str(reset_token)
		self.startService()

	def is_auth(self):
		return self.refresh_token is not None and self.is_authenticated

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

		user_feeds = {
			#"my_subscriptions": "favorites",
			"my_favorites": "favorites",
			"my_history": "watchHistory",
			"my_likes": "likes",
			"my_watch_later": "favorites",
			"my_uploads": "uploads",
		}

		if feedname in user_feeds:

			playlistId = self.getUserPlaylist(user_feeds.get(feedname))
			if playlistId is None:
				return

			return self.request(YoutubeRequests.PlaylistRequest(self.yt_service, playlistId), callback, errorback)

		if feedname in ("hd", "most_popular", "most_shared", "on_the_web"):
			if feedname == "hd":
				url = "http://gdata.youtube.com/feeds/api/videos/-/HD"
			else:
				url = url + feedname
		elif feedname in ("top_rated","most_viewed","recently_featured","top_favorites","most_recent","most_discussed","most_linked","most_responded"):
			pass

		return self.search(searchTerms="test", callback=callback, errorback=errorback)

	def getUserPlaylist(self, name):
		if self.channel_playlists is None:
			self.channel_playlists = self.yt_service.channels().list(mine=True, part="contentDetails").execute()

		try:
			return self.channel_playlists['items'][0]["contentDetails"]["relatedPlaylists"][name]
		except KeyError:
			return None

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

		return self.request(YoutubeRequests.SearchRequest(self.yt_service, {
			"maxResults": maxResults,
			"order": orderby,
			"q": searchTerms,
			"publishedAfter": publishedAfter,
		}), callback, errorback)


	def request(self, request = None, callback = None, errorback = None):
		print "[MyTube] MyTubePlayerService - request()"
		self.feedentries = []
		self.currentPage = 1

		self.lastRequest = request

		queryThread = YoutubeQueryThread(request, {}, self.gotFeed, self.gotFeedError, callback, errorback, self.yt_service)
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

		if self.lastRequest is None:
			print "lastRequest empty"
			return

		page_token = self.lastRequest.getAndActivateNextPage()
		if page_token is None:
			print "page_token empty"
			return

		print "next page" + page_token

		queryThread = YoutubeQueryThread(self.lastRequest, {}, self.gotFeed, self.gotFeedError, callback, errorback, self.yt_service)
		queryThread.start()

		# todo: not here, its async
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

	def SubscribeToUser(self, channelId):

		if channelId is None or len(channelId) == 0:
			return _('Unknown error')

		request = self.yt_service.subscriptions().insert(
			part="snippet",
			body=dict(
				snippet=dict(
					resourceId=dict(
						channelId=channelId
					)
				)
			)
		)

		try:
			request.execute()

			print '[MyTube] MyTubePlayerService: New subscription added'
			return _('New subscription added')
		except HttpError, err:
			if err.resp.get('content-type', '').startswith('application/json'):
				try:
					print '[MyTube] MyTubePlayerService: subscription error ' + json.loads(err.content)['error']['errors'][0]['reason']
					return str('Error' + json.loads(err.content)['error']['errors'][0]['reason'])
				except KeyError:
					pass

			return str('Error: ' + str(err))
	
	def addToFavorites(self, video_id):

		playlist_id = self.getUserPlaylist('favorites')
		if playlist_id is None:
			return

		request = self.yt_service.playlistItems().insert(
			part="snippet",
			body=dict(
				snippet=dict(
					playlistId=playlist_id,
					resourceId=dict(
						kind='youtube#video',
						videoId=video_id
					)
				),
			)
		)

		try:
			request.execute()
		except HttpError, err:
			if err.resp.get('content-type', '').startswith('application/json'):
				try:
					print '[MyTube] MyTubePlayerService: favorites error ' + json.loads(err.content)['error']['errors'][0]['reason']
					return str('Error' + json.loads(err.content)['error']['errors'][0]['reason'])
				except KeyError:
					pass

			return str('Error: ' + str(err))

		print '[MyTube] MyTubePlayerService: Video successfully added to favorites'
		return _('Video successfully added to favorites')
	
	def getTitle(self):
		return ""

	def getEntries(self):
		return self.feedentries

	def itemCount(self):
		return ""

	def getTotalResults(self):
		try:
			return self.feed["pageInfo"]["totalResults"]
		except KeyError:
			return 0

	def getNextFeedEntriesURL(self):
		try:
			return self.feed["nextPageToken"]
		except KeyError:
			print "error in getNextFeedEntriesURL"
			return None

	def getCurrentPage(self):
		return self.currentPage

class YoutubeQueryThread(Thread):
	def __init__(self, youtube_request, args, gotFeed, gotFeedError, callback, errorback, youtube):
		Thread.__init__(self)
		self.messagePump = ePythonMessagePump()
		self.messages = ThreadQueue()
		self.gotFeed = gotFeed
		self.gotFeedError = gotFeedError
		self.callback = callback
		self.errorback = errorback
		self.youtube_request = youtube_request
		self.youtube = youtube
		self.args = args
		self.canceled = False
		#self.messagepPump_conn = self.messagePump.recv_msg.connect(self.finished)
		self.messagePump.recv_msg.get().append(self.finished)

	def cancel(self):
		self.canceled = True

	def run(self):

		try:

			search_videos = self.youtube_request.getResponse()

			if search_videos is None or len(search_videos.get("items", [])) == 0:
				self.messages.push((False, "nothing found", self.errorback))
				self.messagePump.send(0)
				return

			video_response = self.youtube_request.getYoutubeService().videos().list(
				id=",".join(search_videos.get("items", [])),
				part='id,snippet,recordingDetails,statistics,contentDetails'
			).execute()

			search_videos['items'] = video_response.get("items", [])

			self.messages.push((True, search_videos, self.callback))
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

