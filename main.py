#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import json
import webapp2
from webapp2_extras import sessions

from google.appengine.api import images
from google.appengine.ext import blobstore
from google.appengine.ext import ndb

import facebook
import gcs
import models
from models import *
import utils
import searchengine as se

from jinja2 import Template
from jinja2 import FileSystemLoader
from jinja2.environment import Environment

env = Environment()
env.loader = FileSystemLoader('./templates')

FACEBOOK_APP_ID = "276572495886627"
FACEBOOK_APP_SECRET = "4a2250bfce16f1a9c110038ace5f464f"

config = {}
config['webapp2_extras.sessions'] = dict(secret_key='4a2250bfce16f1a9c110038ace5f464f')

PHOTO_MAX_SIZE = 2560

class BaseHandler(webapp2.RequestHandler):
    def __init__(self, request, response):
        self.initialize(request, response)

        
    """Provides access to the active Facebook user in self.current_user

    The property is lazy-loaded on first access, using the cookie saved
    by the Facebook JavaScript SDK to determine the user ID of the active
    user. See http://developers.facebook.com/docs/authentication/ for
    more information.
    """
    @property
    def current_user(self):
        if self.session.get("user"):
            # User is logged in
            return self.session.get("user")
        else:
            # Either used just logged in or just saw the first page
            # We'll see here
            cookie = facebook.get_user_from_cookie(self.request.cookies,
                                                   FACEBOOK_APP_ID,
                                                   FACEBOOK_APP_SECRET)
            if cookie:
                # Okay so user logged in.
                # Now, check to see if existing user
                user = User.get_user(cookie["uid"], User.OAUTH_FACEBOOK)
                if not user:
                    # Not an existing user so get user info
                    graph = facebook.GraphAPI(cookie["access_token"])
                    profile = graph.get_object("me")
                    profile_photo = graph.get_object("me/picture", redirect=0, height=200, width=200, type="normal")
                    user = User(
                        oauth_uid=str(profile["id"]),
                        name=profile["name"],
                        oauth_provider=User.OAUTH_FACEBOOK,
                        profile_picture=profile_photo['data']['url'],
                        access_token=cookie["access_token"],
                        email=profile['email'],
                        timezone=profile['timezone']
                    )
                    user.put()
                    se.index_user(user)
                    #find friends
                    user.add_facebook_friends(graph)
                elif user.access_token != cookie["access_token"]:
                    user.access_token = cookie["access_token"]
                    graph = facebook.GraphAPI(cookie["access_token"])
                    profile_photo = graph.get_object("me/picture", redirect=0, height=200, width=200, type="normal")
                    user.profile_picture=profile_photo['data']['url']
                    user.put()
                # User is now logged in
                self.session["user"] = dict(
                    name=user.name,
                    profile_picture=user.profile_picture,
                    id=user.key.integer_id(),
                    oauth_uid=user.oauth_uid,
                    access_token=user.access_token,
                    timezone=user.timezone
                )
                return self.session.get("user")
        return None
        
    @property
    def template_values(self):
        values = {
            'user' : self.current_user,
            'facebook_app_id':FACEBOOK_APP_ID
        }
        return values
        
    def dispatch(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html

        """
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html

        """
        return self.session_store.get_session()
        
    def send_json(self, obj):
        self.response.out.write(json.dumps(obj))

class LogoutHandler(BaseHandler):
    def get(self):
        if self.current_user is not None:
            self.session['user'] = None

        self.redirect('/')

class MainHandler(BaseHandler):
    def get(self):
        current_user = self.current_user
        is_user = current_user != None
        template_values = {}
        if(is_user):
            t = env.get_template('index.html')
        else:
            t = env.get_template('welcome.html')
        
        template_values = dict(list(template_values.items()) + list(self.template_values.items()))    
        self.response.out.write(t.render(template_values))
        
class EventHandler(BaseHandler):
    def get(self, id):
        user = self.current_user
        if user and id:
            user_key = User.parse_key(user['id'])
            results = Event.query(Event._key == Event.parse_key(id)).filter(Event.who_can_see == user_key).fetch(1)
            if len(results) > 0:
                e = results[0]
                return self.send_json(e.to_dict())
        self.send_json(False)
        
    def post(self, id=None):
        user = self.current_user
        data = json.loads(self.request.get("data"))
        if user:
            #TODO check owner
            owner = User.parse_key(user['id'])
            e = Event(parent=owner)
            if 'desc' in data:
                e.description = models.escape(data['desc'], link=True, br=True)
            if 'pid' in data:
                photo = Photo.from_id(data['pid'])
                if photo:
                    photo.draft = False
                    photo.put()
                    e.photo = photo.key
            if 'event_time' in data:
                e.event_time = datetime.strptime(data['event_time'], models.DATETIME_FORMAT)
            if 'loc' in data:
                loc = data['loc']
                e.location = ndb.GeoPt(loc['lat'], loc['lng'])
            if 'people' in data:
                #TODO check if people who has tagged is friend, and no repeated
                e.people = [User.parse_key(user_key) for user_key in data['people']]
            if 'tags' in data:
                tag = Tag.from_user_id(owner.integer_id(), auto_add=True)
                tags = [models.escape(t) for t in data['tags']]
                tag.add_multi(tags)
                e.tags = tags
            e.who_can_see = [owner] + e.people
            e.put()
            return self.send_json(e.to_dict())
        self.send_json(False)
        
class EventsHandler(BaseHandler):
    def get(self):
        user = self.current_user
        if user:
            q = Event.query(Event.who_can_see == User.parse_key(user['id'])).order(-Event.event_time)
            tags = self.request.get("tags")
            if tags:
                for tag in tags.split(","):
                    q = q.filter(Event.tags == tag)
            users = self.request.get("u")
            if users:
                for user_id in users.split(","):
                    q = q.filter(Event.people == User.parse_key(user_id))
            events = [r.to_dict() for r in q]
            return self.send_json(events)
        self.send_json(False)
        
class PhotoHandler(BaseHandler):
    
    @utils.timing
    def post(self):
        user = self.current_user
        if not user:
            self.error(403)
            return
        upload_files = self.request.POST.getall('files')
        for file in upload_files:
            """ @utils.timing
            def parse_exif_by_pil(file):
                image = Image.open(StringIO.StringIO(file.value))
                original_exif = image._getexif()
                exif = {}
                for key, value in EXIF_TAGS.items():
                    exif[key] = original_exif[value]
                logging.info(exif)
            parse_exif_by_pil(file)"""
            #dummy transforms for getting exif
            
            @utils.timing
            def read_image(file_content):
                img = images.Image(file_content)
                img.resize(100, 100)
                img.execute_transforms(parse_source_metadata=True)
                return img
            img = read_image(file.value)
            w = img.width
            h = img.height
            exif = img.get_original_metadata()
            logging.info(exif)
            
            #real transforms
            @utils.timing
            def resize_image(file_content):
                return images.resize(file_content, PHOTO_MAX_SIZE, PHOTO_MAX_SIZE, output_encoding=images.JPEG, correct_orientation=images.CORRECT_ORIENTATION)
            imgfile = resize_image(file.value)
            
            @utils.timing
            @ndb.transactional
            def do_transaction():
                photo = Photo(width=w, height=h, exif=exif)
                PhotoHandler.apply_exif_for_photo(photo, exif)
                photo.put()            
                return photo
                
            photo = do_transaction()

            filename = "%s/%d" % (user['id'], photo.id)
            blob_key = gcs.create_file(filename, imgfile)
            
            @utils.timing
            def get_serving_url(blob_key):
                url = images.get_serving_url(blob_key, size=images.IMG_SERVING_SIZES_LIMIT, secure_url=True)            
                return url.replace("=s%d" % (images.IMG_SERVING_SIZES_LIMIT) , "=s")
                
            url = get_serving_url(blob_key)
            photo.blob = blob_key
            photo.thumb_url = url
            photo.put()

            self.send_json(photo.to_dict())
            return
        self.send_json(False)
        
    @staticmethod
    def apply_exif_for_photo(photo, exif):
        if 'DateTimeDigitized' in exif:
            str_datetime = exif['DateTimeDigitized']
            if "/" in str_datetime:
                original_time = datetime.strptime(str_datetime, "%Y/%m/%d %H:%M:%S")
            else:
                original_time = datetime.strptime(str_datetime, "%Y:%m:%d %H:%M:%S")
        else:
            original_time = datetime.today()
        with_gps_tag = 'GPSDateStamp' in exif and 'GPSTimeStamp' in exif
        utc = None
        if with_gps_tag:
            utc = datetime.strptime(exif['GPSDateStamp'], "%Y:%m:%d")     
            hour = int(str(exif['GPSTimeStamp']).split(":")[0])
            utc = utc.replace(hour=hour, minute=original_time.minute, second=original_time.second)
        else:
            utc = original_time
        photo.utc = utc
        photo.original_time = original_time
        
        if 'GPSLatitude' in exif and 'GPSLongitude' in exif:
            photo.location = ndb.GeoPt(exif['GPSLatitude'], exif['GPSLongitude'])
        photo.exif = exif
        
class FriendHandler(BaseHandler):
    def get(self):
        current_user = self.current_user
        if current_user:
            user = User.from_id(self.current_user['id'])
            f = user.get_friends()
            friends = []
            for s in f.suggestions:
                friends.append(s.get().to_dict())
            return self.send_json(friends)
        self.send_json(False)
        
class TagHandler(BaseHandler):
    def get(self):
        current_user = self.current_user
        if current_user:
            tag = Tag.from_user_id(self.current_user['id'])
            return self.send_json(tag.tags if tag else [])
        self.send_json(False)

class DemoHandler(BaseHandler):
    def get(self):
        results = Event.query().fetch(1000)
        updated = []
        for i in range(len(results)):
            r = results[i]
            if i >= 8:
                continue
            r.location = ndb.GeoPt(i * 10, i * 10)
            updated.append(r)
        ndb.put_multi(updated)
        
        user = User(name="Noah Wu", profile_picture="https://fbcdn-profile-a.akamaihd.net/hprofile-ak-xpa1/v/t1.0-1/c50.0.200.200/p200x200/10306170_10152250910194398_4038395448859091170_n.jpg?oh=aac0612de87d78dacd02d4b3450da342&oe=54B45EE1&__gda__=1421432074_7efe9b9f1718f166cadd91f4abf28be9")
        user.put()
        current_user = self.current_user
        if current_user:
            user = User.from_id(self.current_user['id'])
            f = user.get_friends()
            f.suggestions.append(user.key)
            f.put()

app = webapp2.WSGIApplication([
    ('/_api/event/([^/]+)?', EventHandler),
    ('/_api/event', EventHandler),
    ('/_api/events', EventsHandler),
    ('/_api/me/friends', FriendHandler),
    ('/_api/photo', PhotoHandler),
    ('/_api/tag', TagHandler),
    ('/_dev/demo', DemoHandler),
    ('/logout', LogoutHandler),
    ('/', MainHandler)
], debug=True
, config=config)
