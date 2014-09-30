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

import facebook
import gcs
import models
from models import *
import utils

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
            e = Event.from_id(id, parent=user['id'])
            if e:
                return self.send_json(e.to_dict())
        self.send_json(False)
        
    def post(self):
        user = self.current_user
        data = json.loads(self.request.get("data"))
        if user:
            e = Event(parent=User.parse_key(user['id']))
            if 'desc' in data:
                e.description = models.escape(data['desc'], link=True, br=True)
            if 'pid' in data:
                photo = Photo.from_id(data['pid'])
                if photo:
                    photo.draft = False
                    photo.put()
                    e.photo = photo.key
            e.put()
            return self.send_json(e.to_dict())
        self.send_json(False)
        
class EventsHandler(BaseHandler):
    def get(self):
        user = self.current_user
        if user:
            q = Event.query(ancestor=User.parse_key(user['id'])).order(-Event.event_time)
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
        original_time = datetime.strptime(exif['DateTimeDigitized'], "%Y:%m:%d %H:%M:%S")     
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
            

app = webapp2.WSGIApplication([
    ('/_api/event/([^/]+)?', EventHandler),
    ('/_api/event', EventHandler),
    ('/_api/events', EventsHandler),
    ('/_api/photo', PhotoHandler),
    ('/', MainHandler)
], debug=True
, config=config)
