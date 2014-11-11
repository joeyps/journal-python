import datetime

class UtcTzinfo(datetime.tzinfo):
  def utcoffset(self, dt): return datetime.timedelta(0)
  def dst(self, dt): return datetime.timedelta(0)
  def tzname(self, dt): return 'UTC'
  def olsen_name(self): return 'UTC'
  
class EstTzinfo(datetime.tzinfo):
  def utcoffset(self, dt): return datetime.timedelta(hours=-5)
  def dst(self, dt): return datetime.timedelta(0)
  def tzname(self, dt): return 'EST+05EDT'
  def olsen_name(self): return 'US/Eastern'

class PstTzinfo(datetime.tzinfo):
  def utcoffset(self, dt): return datetime.timedelta(hours=-8)
  def dst(self, dt): return datetime.timedelta(0)
  def tzname(self, dt): return 'PST+08PDT'
  def olsen_name(self): return 'US/Pacific'
  
TZINFOS = {
  'utc': UtcTzinfo(),
  'est': EstTzinfo(),
  'pst': PstTzinfo(),
}

utc = TZINFOS["utc"]