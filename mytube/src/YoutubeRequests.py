class YoutubeRequest:

	response = None
	args = {}
	yt_service = None
	next_page_token = None

	def __init__(self, yt_service, args):
		self.yt_service = yt_service
		self.args = args

	def getYoutubeService(self):
		return self.yt_service

	def getResponse(self):
		pass

	def getAndActivateNextPage(self):
		if self.response is None:
			return None

		try:
			self.next_page_token = self.response["nextPageToken"]
			return self.next_page_token
		except KeyError:
			return None

	def prepareArgs(self):
		args = self.args
		if self.next_page_token is not None:
			args['pageToken'] = self.next_page_token

		return args

class PlaylistRequest(YoutubeRequest):

	def __init__(self, yt_service, playlist_id):
		YoutubeRequest.__init__(self, yt_service, {
			'playlistId': playlist_id,
			'part': "snippet",
			'maxResults': 50
		})

	def getResponse(self):

		args = self.prepareArgs()

		request = self.yt_service.playlistItems().list(**args)
		self.response = request.execute()

		ids = []

		for playlist_item in self.response["items"]:
			ids.append(playlist_item["snippet"]["resourceId"]["videoId"])

		self.response['items'] = ids

		return self.response

class SearchRequest(YoutubeRequest):

	def getResponse(self):

		args = self.prepareArgs()

		args['part'] = 'id'
		self.response = self.yt_service.search().list(**args).execute()

		ids = []

		for search_result in self.response.get("items", []):
			ids.append(search_result["id"]["videoId"])

		self.response['items'] = ids

		return self.response