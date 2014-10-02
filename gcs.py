from __future__ import with_statement

import cloudstorage as gcs

from google.appengine.ext import blobstore

import utils

BUCKET = "/those-days.appspot.com/"

@utils.timing
def create_file(filename, file):
  """Create a GCS file with GCS client lib.

  Args:
    filename: GCS filename.

  Returns:
    The corresponding string blobkey for this GCS file.
  """
  # Create a GCS file with GCS client.
  with gcs.open(BUCKET + filename, 'w') as f:
    f.write(file)

  # Blobstore API requires extra /gs to distinguish against blobstore files.
  blobstore_filename = '/gs' + BUCKET + filename
  # This blob_key works with blobstore APIs that do not expect a
  # corresponding BlobInfo in datastore.
  gs_key = blobstore.create_gs_key(blobstore_filename)
  key = blobstore.BlobKey(gs_key)
  return key