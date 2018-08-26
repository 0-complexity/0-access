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
from whoosh.qparser import QueryParser
from whoosh.index import create_in, exists_in, open_dir
from whoosh.fields import Schema, ID, TEXT, DATETIME

class Indexor():


    def __init__(self):
        schema = Schema(session=ID(stored=True), content=TEXT(stored=True), start=DATETIME(stored=True), 
                        end=DATETIME(stored=True), username=TEXT(stored=True), remote=TEXT(stored=True))
        if exists_in("/var/recordings/index"):
            self.idx = open_dir("/var/recordings/index")
        else:
            self.idx = create_in("/var/recordings/index", schema)

    def index(self, session, start, end, username, remote):
        recording = "/var/recordings/%s.json" % session
        if not os.path.exists(recording):
            return
        writer = self.idx.writer()
        try:
            writer.add_document(session=session, start=start, end=end, 
                                content=self._get_content(recording), username=username, 
                                remote=remote)
        finally:
            writer.commit()


    def _get_content(self, recording):
        import io
        import ijson
        text = io.StringIO()
        with open(recording, "rb") as f:
            for lines in ijson.items(f, 'stdout.item'):
                text.write(lines[1])
        return text.getvalue()

    def search(self, query, page, username, remote):
        start = time.time()
        if username:
            query += " username:%s" % username
        if remote:
            query += " remote:%s" % remote
        parser = QueryParser("content", schema=self.idx.schema)
        query = parser.parse(query)
        with self.idx.searcher() as s:
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

