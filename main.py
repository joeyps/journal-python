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
import webapp2
from webapp2_extras import sessions

import facebook
from models import *

from jinja2 import Template
from jinja2 import FileSystemLoader
from jinja2.environment import Environment

env = Environment()
env.loader = FileSystemLoader('./templates')

FACEBOOK_APP_ID = "276572495886627"
FACEBOOK_APP_SECRET = "4a2250bfce16f1a9c110038ace5f464f"

config = {}
config['webapp2_extras.sessions'] = dict(secret_key='4a2250bfce16f1a9c110038ace5f464f')

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
        
    def send_result(self, obj):
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

app = webapp2.WSGIApplication([
    ('/', MainHandler)
], debug=True
, config=config)
