import logging

from google.appengine.api import search

from models import User

_INDEX_MAIN = "INDEX_MAIN"

FIELD_PATTERNS = 'patterns'

def user_to_doc(user):
    doc = search.Document(
        # Setting the doc_id is optional. If omitted, the search service will create an identifier.
        
        #Updating documents
        #A document cannot be changed once you've added it to an index. You can't add or remove fields, or change a field's value. However, you can replace the document with a new document that has the same doc_id.
        doc_id = 'U-%s' % (str(user.id)),
        fields=[
            search.TextField(name='id', value=str(user.id)),
            search.TextField(name='name', value=user.name),
            search.TextField(name='profile_picture', value=user.profile_picture),
            search.TextField(name=FIELD_PATTERNS, value=','.join(tokenize_autocomplete(user.name)))
           #,
#           search.NumberField(name='number_of_visits', value=7), 
#           search.DateField(name='last_visit', value=datetime.now()),
#           search.DateField(name='birthday', value=datetime(year=1960, month=6, day=19)),
#           search.GeoField(name='home_location', value=search.GeoPoint(37.619, -122.37))
           ])
    return doc
    
def tokenize_autocomplete(phrase):
    patterns = []
    for word in phrase.split():
        j = 1
        while True:
            for i in range(len(word) - j + 1):
                patterns.append(word[i:i + j])
            if j == len(word):
                break
            j += 1
    return patterns
    
def index_users():
    users = User.query().fetch(1000)
    docs = []
    for user in users:
        doc = user_to_doc(user)
        docs.append(doc)
    index = search.Index(name=_INDEX_MAIN)
    try:
        index.put(docs)
        logging.info('[index] index %s' % (docs))
    except search.Error:
        logging.exception('[index] users put failed')

def index_user(user):
    if user:
        try:
            index = search.Index(name=_INDEX_MAIN)
            doc = user_to_doc(user)
            index.put(doc)
        except search.Error:
            logging.exception('[index] user %s put failed' % (str(user.id)))
        

def delete_main():
    delete_all_in_index(_INDEX_MAIN)

def delete_all_in_index(index_name):
    """Delete all the docs in the given index."""
    doc_index = search.Index(name=index_name)

    # looping because get_range by default returns up to 100 documents at a time
    while True:
        # Get a list of documents populating only the doc_id field and extract the ids.
        document_ids = [document.doc_id
                        for document in doc_index.get_range(ids_only=True)]
        if not document_ids:
            break
        # Delete the documents for the given ids from the Index.
        doc_index.delete(document_ids)
        
def query(pattern):
    index = search.Index(name=_INDEX_MAIN)
    query_string = "%s: %s" % (FIELD_PATTERNS, pattern)
    try:
        result = index.search(query_string) 
        results = []
        for doc in result.results:
            fields = {}
            for f in doc.fields:
                if f.name != FIELD_PATTERNS:
                    fields[f.name] = f.value
            results.append({'value': fields['name'], 'data': fields})
        logging.info(results)
        return {'query': pattern, 'suggestions' : results }
        # Iterate over the documents in the results
        #for doc in results:
            # handle results

    except search.Error:
        logging.exception('Search failed')
    return []