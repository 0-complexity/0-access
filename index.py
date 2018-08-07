#!/usr/bin/python3
#
# Full text indexing of 
#
import pickle
import sys
import math
import time
import os
from subprocess import Popen, PIPE


class Indexor():


    def __init__(self):
        self._process = Popen(['python3', __file__], stdout=PIPE, stdin=PIPE)


    def stop(self):
        pickle.dump(("stop", None), self._process.stdin)
        self._process.stdin.flush()


    def _offload(self, method, *args):
        pickle.dump((method, args), self._process.stdin, protocol=pickle.HIGHEST_PROTOCOL)
        self._process.stdin.flush()
        success, result = pickle.load(self._process.stdout)
        return result


    def ping(self):
        return self._offload("_ping")
    

    def index(self, session, start, end, username, remote):
        return self._offload("_index", session, start, end, username, remote)

    
    def search(self, query, page, user, remote):
        return self._offload("_search", query, page, user, remote)


def _ping():
    return "pong"


def _get_content(recording):
    import io
    import ijson
    text = io.StringIO()
    with open(recording, "rb") as f:
        for lines in ijson.items(f, 'stdout.item'):
            text.write(lines[1])
    return text.getvalue()


def _index(session, start, end, username, remote):
    recording = "/var/recordings/%s.json" % session
    if not os.path.exists(recording):
        return
    writer = idx.writer()
    try:
        writer.add_document(session=session, start=start, end=end, 
                            content=_get_content(recording), username=username, 
                            remote=remote)
    finally:
        writer.commit()


def _search(query, page, username, remote):
    start = time.time()
    if username:
        query += " username:%s" % username
    if remote:
        query += " remote:%s" % remote
    parser = QueryParser("content", schema=idx.schema)
    query = parser.parse(query)
    with idx.searcher() as s:
        search_results = s.search_page(query, page, pagelen=10, terms=True)
        hits = list()
        result = dict(total_pages=math.ceil(len(search_results) / 10), page=hits)
        for hit in search_results:
            hits.append(dict(terms=[term.decode() for _, term in hit.matched_terms()], 
                             session=hit['session'],
                             username=hit['username'],
                             remote=hit['remote'],
                             start=hit['start'].timestamp(),
                             end=hit['end'].timestamp(),
                             highlights=hit.highlights("content")))
    result["stats"] = "Found %s hits in %s seconds." % (len(search_results), time.time() - start)
    return result


if __name__ == "__main__":
    from whoosh.qparser import QueryParser
    from whoosh.index import create_in, exists_in, open_dir
    from whoosh.fields import Schema, ID, TEXT, DATETIME
    schema = Schema(session=ID(stored=True), content=TEXT(stored=True), start=DATETIME(stored=True), 
                    end=DATETIME(stored=True), username=TEXT(stored=True), remote=TEXT(stored=True))
    if exists_in("/var/recordings/index"):
        idx = open_dir("/var/recordings/index")
    else:
        idx = create_in("/var/recordings/index", schema)
    stdout = sys.stdout if getattr(sys.stdout, 'buffer') else sys.__stdout__
    while True:
        function, args = pickle.load(sys.stdin.buffer.raw)
        if function == "stop":
            break
        try:
            function = globals()[function]
            result = function(*args)
            pickle.dump((True, result), stdout.buffer, protocol=pickle.HIGHEST_PROTOCOL)
        except BaseException as e:
            pickle.dump((False, e), stdout.buffer, protocol=pickle.HIGHEST_PROTOCOL)
        stdout.buffer.flush()
