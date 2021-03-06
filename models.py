import cgi
import random
import re
import logging
from datetime import datetime, timedelta

from google.appengine.ext import ndb
from google.appengine.ext import db
from google.appengine.datastore.datastore_query import Cursor

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TIMESTAMP_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"

PERMISSIONS = {
    'private':1000001,
    'public':1000002
    }

class BaseModel(ndb.Model):
    
    @property
    def id(self):
      return self.key.integer_id()
    
    @classmethod
    def from_id(cls, id, parent=None):
        key = cls.parse_key(id, parent)
        if key:
            return key.get()
        return None
    
    @classmethod        
    def parse_key(cls, id, parent=None):
        try:
            if parent:
                return ndb.Key(cls, long(id), parent=cls._get_parent_cls().parse_key(parent))
            else:
                return ndb.Key(cls, long(id))
        except ValueError:
            return None
            
    @classmethod        
    def _get_parent_cls(cls):
        return None         

class User(BaseModel):
    OAUTH_GOOGLE = "google"
    OAUTH_FACEBOOK = "facebook"
    OAUTH_PROVIDERS = [ OAUTH_GOOGLE, OAUTH_FACEBOOK ]
    
    name = ndb.StringProperty()
    password = ndb.StringProperty(indexed=False)
    email = ndb.StringProperty()
    timezone = ndb.IntegerProperty(default=0)
    oauth_provider = ndb.StringProperty()
    oauth_uid = ndb.StringProperty()
    profile_picture = ndb.StringProperty()
    access_token = ndb.StringProperty()
    num_following = ndb.IntegerProperty(default=0)
    num_follower = ndb.IntegerProperty(default=0)
    latest_sign_in_time = ndb.DateTimeProperty(auto_now=True)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    def update(self, data):
        if not data:
            return
        if 'timezone' in data:
            self.timezone = data['timezone']
        self.put()
    
    def get_friends(self):
        f = Friends.query(ancestor=self.key).fetch(1)
        if len(f) > 0:
            return f[0]
        else:
            friends = Friends(parent=self.key)
            friends.following = []
            friends.suggestions = []
            friends.follower = []
            return friends
            
    def get_journeys(self):
        return Journey.query(Journey.deleted == False, ancestor=self.key).order(-Journey.created_time)
     
    def add_facebook_friends(self, fb_graph):
        fb_users = fb_graph.get_object("me/friends")
        fb_users = fb_users['data']
        
        other_users = []
        for fb_user in fb_users:
            other_user = User.get_user(fb_user['id'], User.OAUTH_FACEBOOK)
            if other_user:
                other_users.append(other_user)
        
        @ndb.transactional(xg=True)
        def do_transaction(user, other_users):
            batch_updated = []
            friends = user.get_friends()
            for other_user in other_users:
                if other_user and other_user.key not in friends.suggestions:
                    friends.suggestions.append(other_user.key)
                    other_user_friends = other_user.get_friends()
                    if user.key not in other_user_friends.suggestions:
                        other_user_friends.suggestions.append(user.key)
                        batch_updated.append(other_user_friends)
            batch_updated.append(friends)
            ndb.put_multi(batch_updated)
            
        do_transaction(self, other_users)
            
    def follow_user(self, id):
        @ndb.transactional(xg=True)
        def do_transaction():
            friends = self.get_friends()
            user = User.from_id(id)
            if user and user.key not in friends.following and self.id != user.id:
                friends.following.append(user.key)
                if user.key in friends.suggestions:
                    friends.suggestions.remove(user.key)
                friends.put()
                Notification.post(user.key, Notification.MESSAGES['friend_following'], self.key)
                return True
            return False
        return do_transaction()
        
    def unfollow_user(self, id):
        friends = self.get_friends()
        key = User.parse_key(id)
        if key:
            if key in friends.following:
                friends.following.remove(key)
            if key not in friends.suggestions and self.id != key.integer_id():
                friends.suggestions.append(key)
            friends.put()
            return True
        return False
        
    def is_following(self, id):
        key = User.parse_key(id)
        friends = self.get_friends()
        if not key:
            return False
        return True if key in friends.following else False
        
    def starJourney(self, id, checked):
        j = Journey.from_id(id)
        if not j:
            return False
        #TODO check permission
        logging.info(checked)
        starred = self.getStarredJourneys()
        if checked:
            if j.key not in starred.journeys:
                starred.journeys.insert(0, j.key)
            starred.put()
            return True
        elif not checked and j.key in starred.journeys:
            starred.journeys.remove(j.key)
            starred.put()
            return False
        return False
            
    def getStarredJourneys(self):
        r = Starred.query(ancestor=self.key).fetch(1)
        if len(r) > 0:
            return r[0]
        else:
            starred = Starred(parent=self.key)
            starred.journeys = []
            return starred
        

    @staticmethod
    def get_user(id, provider=None):
        if not provider:
            return User.from_id(id)
        else:
            if provider not in User.OAUTH_PROVIDERS:
                return None
            id = str(id)
            users = User.query(ndb.AND(User.oauth_provider == provider, User.oauth_uid == id)).fetch(1)
            user = None
            if len(users) > 0:
                user = users[0]
            return user
    
    def to_dict(self):
        d = dict(id=self.id,
                name=self.name,
                profile_picture=self.profile_picture,
                oauth_provider=self.oauth_provider,
                oauth_uid=self.oauth_uid
                )
        return d
        
class AuthToken(BaseModel):
    TOKEN_TYPE = {
        'auth' : 1000
    }
    
    token = ndb.StringProperty(required=True)
    token_type = ndb.IntegerProperty(required=True)
    user = ndb.KeyProperty(kind=User, required=True)
    client = ndb.StringProperty()
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    
    @staticmethod
    def get_by_token(token):
        results = AuthToken.query().filter(AuthToken.token==token).fetch(1)
        if len(results) > 0:
            return results[0]
        return None
    
    @staticmethod
    def add_or_update_token(user_key, token_type, token):
        results = AuthToken.query().filter(AuthToken.user==user_key).filter(AuthToken.token_type==token_type).fetch(1)
        auth_token = None
        if len(results) > 0:
            auth_token = results[0]
            auth_token.token = token
        else:
            auth_token = AuthToken(user=user_key, token_type=token_type, token=token)
        auth_token.put()
        return auth_token
        

class Journey(BaseModel):
    title = ndb.StringProperty()
    description = ndb.TextProperty()
    permission = ndb.IntegerProperty(default=PERMISSIONS['private'])
    #map_bounds = ndb.GeoPtProperty(repeated=True)
    map_center = ndb.GeoPtProperty()
    #location = db.ListProperty(db.Key, default=None)
    date_from = ndb.DateTimeProperty()
    num_days = ndb.IntegerProperty(default=0)
    num_likes = ndb.IntegerProperty(default=0)
    num_comments = ndb.IntegerProperty(default=0)
    deleted = ndb.BooleanProperty(default=False)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
        
    @classmethod        
    def parse_key(cls, urlsafe, parent=None):
        try:
            return ndb.Key(urlsafe=urlsafe)
        except ValueError:
            return None
            
    @classmethod
    def from_id(cls, id, parent=None):
        key = cls.parse_key(id, parent)
        if key:
            j = key.get()
            if j and not j.deleted:
                return j
        return None
        
    @property
    def id(self):
        return self.key.urlsafe()
      
    @property
    def owner(self):
        return self.key.parent()
    
    def post_comment(self, uid, content):
        @ndb.transactional
        def do_transaction():
            user_key = User.parse_key(uid)
            c = Comment.post(self.key, user_key, content)
            if not self.is_owner(uid):
                Notification.post(self.key.parent(), Notification.MESSAGES['journey_comment'], user_key, target=c.key)
            self.num_comments += 1
            self.put()
            return c
        try:
            return do_transaction()
        except db.TransactionFailedError:
            return False
    
    def is_owner(self, uid):
        return self.key.parent().integer_id() == uid
        
    def set_photos_place(self, ids, place):
        keys = []
        for id in ids:
            keys.append(Photo.parse_key(id, parent=self.id))
        photos = ndb.get_multi(keys)
        for p in photos:
            loc = place["loc"]
            #p.location = ndb.GeoPt(loc['lat'], loc['lng'])
            p.place = place
        ndb.put_multi(photos)
        return True
        
    def get_highlight_photos(self, count=8):
        photos = Photo.query(ancestor=self.key).fetch(count*2)
        random.shuffle(photos)
        return photos
        
    def is_starred(self, user_id):
        q = Starred.query(Starred.journeys.IN([self.key]), ancestor=User.parse_key(user_id))
        return q.count() > 0
    
    def like(self, user_key, like):
        @ndb.transactional
        def do_transaction():
            result = Like.post(self.key, user_key, like)
            logging.info(result)
            if result:
                self.num_likes += 1
            else:
                self.num_likes -= 1
            self.num_likes = max(0, self.num_likes)
            self.put()
            if not self.is_owner(user_key.integer_id()):
                Notification.post(self.key.parent(), Notification.MESSAGES['journey_like'], user_key, target=self.key)
            return result
            
        return do_transaction()
    
    def to_dict(self):
        center = dict(lat=self.map_center.lat, lng=self.map_center.lon) if self.map_center else None
        date_from_formatted = formatted_time(self.date_from, from_now=False)
        d = dict(id=self.id,
                title=self.title,
                description=self.description,
                center=center,
                date_from=self.date_from.strftime(DATE_FORMAT) if self.date_from else None,
                date_from_formatted=date_from_formatted.upper() if date_from_formatted else None,
                owner=self.owner.get().to_dict(),
                permission=self.permission,
                num_days=self.num_days,
                num_likes=self.num_likes,
                num_comments=self.num_comments,
                created_time=self.created_time.strftime(DATETIME_FORMAT),
                updated_time=self.created_time.strftime(DATETIME_FORMAT),
                formatted_time=formatted_time(self.created_time),
                photos=[]
                )
        return d
        
class Photo(BaseModel):
    #custom_time = ndb.DateTimeProperty()
    width = ndb.IntegerProperty(required=True)
    height = ndb.IntegerProperty(required=True)
    blob = ndb.BlobKeyProperty()
    thumb_url = ndb.StringProperty(indexed=False)
    exif = ndb.JsonProperty()
    location = ndb.GeoPtProperty()
    utc = ndb.DateTimeProperty()
    draft = ndb.BooleanProperty(default=True)
    original_time = ndb.DateTimeProperty()
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    @classmethod        
    def _get_parent_cls(cls):
        return Journey  
    
    def update(self, data):
        if not data:
            return
        if 'desc' in data:
            self.description = escape(data['desc'], link=True)
        self.put()
        
    def is_owner(self, uid):
        return self.key.parent().parent().integer_id() == uid
    
    def to_dict(self):
        d = dict(id=self.id,
                width=self.width,
                height=self.height,
                original_time=self.original_time.strftime(DATETIME_FORMAT),
                utc=self.utc.strftime(DATETIME_FORMAT),
                thumb_url=self.thumb_url,
                location= { 'lat':self.location.lat, 'lng':self.location.lon } if self.location else None
                )
        return d
        
class Friends(BaseModel):
    following = ndb.KeyProperty(kind=User, repeated=True)
    suggestions = ndb.KeyProperty(kind=User, repeated=True)
    followers = ndb.KeyProperty(kind=User, repeated=True)
    
    def to_dict(self):
        users = ndb.get_multi(self.following)
        following = []
        for user in users:
            following.append(user.to_dict())
        
        users = ndb.get_multi(self.suggestions)
        suggestions = []
        for user in users:
            suggestions.append(user.to_dict())
        d = dict(following=following,
                suggestions=suggestions
                )
        return d
        
class Place(BaseModel):
    name = ndb.StringProperty()
    
class Comment(BaseModel):
    content = ndb.TextProperty(required=True)
    owner = ndb.KeyProperty(kind=User, required=True)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    @classmethod        
    def parse_key(cls, urlsafe, parent=None):
        try:
            return ndb.Key(urlsafe=urlsafe)
        except ValueError:
            return None
        
    @property
    def id(self):
        return self.key.urlsafe()
    
    @staticmethod
    def post(parent_key, user_key, content):
        content = escape(content, link=True)
        c = Comment(parent=parent_key, owner=user_key, content=content)
        c.put()
        return c
    
    @staticmethod
    def get_comments(parent_key, last=5, cursor=None):
        curs = Cursor(urlsafe=cursor)
        comments, next_curs, more = Comment.query(ancestor=parent_key).order(-Comment.created_time).fetch_page(last, start_cursor=curs)
        return comments, (next_curs.urlsafe() if next_curs else None), more
    
    def to_dict(self):
        d = dict(
            id=self.id,
            content=self.content,
            owner=self.owner.get().to_dict(),
            created_time=self.created_time.strftime(DATETIME_FORMAT),
            formatted_created_time=formatted_time(self.created_time)
                )
        return d
        
class Starred(BaseModel):
    journeys = ndb.KeyProperty(kind=Journey, repeated=True)
    
class Like(BaseModel):
    user = ndb.KeyProperty(kind=User, required=True)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    @classmethod
    def post(cls, parent_key, user_key, like):
        result = Like.query(ancestor=parent_key).filter(Like.user == user_key).fetch(1, keys_only=True)
        logging.info("like=%s" % (like))
        if not like and len(result) > 0:
            result[0].delete()
            return False
        elif like:
            if len(result) <= 0:
                like = Like(parent=parent_key, user=user_key)
                like.put()
            return True
        return False
    
    @classmethod    
    def liked(cls, parent_key, user_key):
        return Like.query(ancestor=parent_key).filter(Like.user == user_key).count() > 0
        
class Notification(BaseModel):
    MESSAGES = {
        'friend_following' : 1000001,
        'friend_join' : 1000002,
        'journey_like' : 2000001,
        'journey_comment' : 2000002,
        'journey_star' : 2000003,
        'event_tagged' : 2000004,
        'event_edited' : 2000005,
        'photo_like' : 3000001,
        'photo_comment' : 3000002
    }
    
    msg_type = ndb.IntegerProperty(required=True)
    user = ndb.KeyProperty(kind=User, required=True)
    target = ndb.KeyProperty()
    read = ndb.BooleanProperty(default=False)
    seen = ndb.BooleanProperty(default=False)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    @staticmethod
    def post(target_key, msg_type, user_key, target=None):
        n = Notification(parent=target_key, msg_type=msg_type, user=user_key)
        if target:
            n.target = target
        n.put()
        
    @staticmethod
    def post_multi(target_keys, msg_type, user_key, target=None):
        if (not target_keys) or len(target_keys) == 0:
            return
        updated = []
        for target_key in target_keys:
            n = Notification(parent=target_key, msg_type=msg_type, user=user_key)
            if target:
                n.target = target
            updated.append(n)
        ndb.put_multi(updated)
        
    @staticmethod
    def get_messages(user_key, max_count=10, cursor=None):
        q = Notification.query(ancestor=user_key).order(Notification.created_time)
        return q.fetch_page(max_count, start_cursor=cursor)
        
    @staticmethod
    def get_older_messages(user_key, max_count=10, cursor=None):
        q = Notification.query(ancestor=user_key).order(-Notification.created_time)
        #qi = Notification.query(ancestor=user_key).order(-Notification.created_time).iter()
        #for i in range(10):
        #    logging.info(qi.cursor_before().urlsafe())
        return q.fetch_page(max_count, start_cursor=cursor)
        
    @staticmethod
    def get_unseen_count(user_key, max_count=99):
        return Notification.query(Notification.seen == False, ancestor=user_key).order(-Notification.created_time).count(limit=max_count)
        
    @staticmethod
    def get_message_str(dict_notification):
        n = dict_notification
        msg_type = n['msg_type']
        if msg_type in Notification.MESSAGES.itervalues():
            return {
                Notification.MESSAGES['friend_following']:lambda n : "%s is now following you" % (n['user']['name']),
                Notification.MESSAGES['journey_like']:lambda n : "%s likes your story\"%s\"" % (n['user']['name'], n['target']['title']),
                Notification.MESSAGES['journey_comment']:lambda n : "%s commented on your story: \"%s\"" % (n['user']['name'], escape(n['target']['content'])),
                Notification.MESSAGES['event_tagged']:lambda n : "%s tagged you in an event" % (n['user']['name']),
                Notification.MESSAGES['event_edited']:lambda n : "%s edited an event that you are tagged in" % (n['user']['name'])
            }[msg_type](n)
        else:
            return ""
            
    @staticmethod
    def get_message_link(dict_notification):
        n = dict_notification
        msg_type = n['msg_type']
        if msg_type in Notification.MESSAGES.itervalues():
            return {
                Notification.MESSAGES['friend_following']:lambda n : "/u/%s" % (n['user']['id']),
                Notification.MESSAGES['journey_like']:lambda n : "/journey/%s" % (n['target']['id']),
                Notification.MESSAGES['journey_comment']:lambda n : "/journey/%s" % (Comment.parse_key(n['target']['id']).parent().urlsafe())
            }[msg_type](n)
        else:
            return ""
    
    @staticmethod
    def mark_all_as_unseen(user_key):
        q = Notification.query(Notification.seen == False, ancestor=user_key)
        updated = []
        for r in q:
            r.seen = True
            updated.append(r)
        ndb.put_multi(updated)
        
    @staticmethod
    def mark_as_seen_multi(user_key, keys):
        msgs = ndb.get_multi(keys)
        updated = []
        for msg in msgs:
            if msg.key.parent() == user_key:
                msg.seen = True
                updated.append(msg)
        if len(updated) > 0:
            ndb.put_multi(updated)
    
    def mark_as_read(self):
        self.read = True
        self.put()
        
    @classmethod        
    def _get_parent_cls(cls):
        return User
        
    def to_dict(self):
        target = None
        if self.target:
            target = self.target.get()
        d = dict(
            id=self.id,
            msg_type=self.msg_type,
            user=self.user.get().to_dict(),
            target = target.to_dict() if target else None,
            read = self.read,
            seen = self.seen,
            created_time=self.created_time.strftime(DATETIME_FORMAT)
                )
        message_str = Notification.get_message_str(d)
        #message_link = Notification.get_message_link(d)
        d['message_str'] = message_str
        #d['message_link'] = message_link
        return d

class Tag(BaseModel):
    tags = ndb.StringProperty(repeated=True)
    
    def add_multi(self, tags):
        #TODO tag name doesn't accept symbol (.%^&*()@#$)
        self.tags = self.tags or []
        for tag in tags:
            if tag not in self.tags:
                self.tags.append(tag)
        self.tags = sorted(self.tags)
        self.put()
    
    @staticmethod
    def from_user_id(user_id, auto_add=False):
        user_key = User.parse_key(user_id)
        results = Tag.query(ancestor=user_key).fetch(1)
        if len(results) > 0:
            return results[0]
        elif auto_add:
            tag = Tag(parent=user_key, tags=[])
            tag.put()
            return tag
    
    @classmethod        
    def _get_parent_cls(cls):
        return User      
    
    def to_dict(self):
        d = dict(
            tags=self.tags if self.tags else []
                )
        return d
        
class Event(BaseModel):
    description = ndb.TextProperty()
    photo = ndb.KeyProperty(kind=Photo)
    people = ndb.KeyProperty(kind=User, repeated=True)
    tags = ndb.StringProperty(repeated=True)
    event_time = ndb.DateTimeProperty()
    location = ndb.GeoPtProperty()
    place = ndb.JsonProperty()
    who_can_see = ndb.KeyProperty(kind=User, repeated=True)
    created_time = ndb.DateTimeProperty(auto_now_add=True)
    updated_time = ndb.DateTimeProperty(auto_now=True)
    
    def is_owner(self, user_id):
        return self.key.parent().integer_id() == user_id
    
    @classmethod        
    def parse_key(cls, urlsafe, parent=None):
        try:
            return ndb.Key(urlsafe=urlsafe)
        except ValueError:
            return None
        
    @property
    def id(self):
        return self.key.urlsafe()
    
    @classmethod        
    def _get_parent_cls(cls):
        return User      
    
    def to_dict(self):
        d = dict(
            id=self.id,
            description=self.description,
            photo=self.photo.get().to_dict() if self.photo else None,
            event_time=self.event_time.strftime(DATETIME_FORMAT),
            people=[user.integer_id() for user in self.people] if self.people else [],
            tags=(self.tags or []),
            location= { 'lat':self.location.lat, 'lng':self.location.lon } if self.location else None,
            place=self.place,
            owner={
                'id':self.key.parent().integer_id()
            }
                )
        return d

def escape(s, link=False):
    #Deprecated since python v3.2
    s = cgi.escape(s, quote=True)
    s = s.replace("&amp;nbsp;", "&nbsp;")
#    if link:
#        s = _parse_link(s)
    return s
   
def _parse_link(text):
    def handleMatch(m):
        url = m.group(0)
        endAtComma = False
        if url[-1] == ",":
            endAtComma = True
            url = url[:-1]
        return "<a target='_blank' href='%s'>%s</a>%s" % ( ("http://" + url) if url.startswith('www') else url, url, ("," if endAtComma else ""))
    return re.sub(r"((https?://|www\.)[^\s]+)", handleMatch, text)
    
def formatted_time(time, from_now=True):
    if not time:
        return None
    now = datetime.today()
    target = time
    diff = now - target
    if from_now and diff.days ==0:
        seconds = diff.total_seconds()
        hours = int(seconds / 60 / 60)
        if hours > 0:
            return "%d hr%s" % (hours, "s" if hours > 1 else "")
        else:
            mins = int(seconds / 60)
            if mins > 0:
                return "%d min%s" % (mins, "s" if mins > 1 else "")
            else:
                return "Just now"
    elif from_now and diff.days == 1:
        return "Yesterday"
    elif from_now and diff.days >= 2 and diff.days <=3:
        return "%d days ago" % (diff.days)
    else:
        return "%s %d" % (time.strftime("%b"), time.day)
        