#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
From a taxonomy ID retrieves all the nucleotide sequences
It returns a multiFASTA nuc/prot file

Entrez Database  UID common name  E-utility Database Name
Nucleotide       GI number        nuccore
Protein          GI number        protein

Retrieve strategy:

esearch to get total number of UIDs (count)
esearch to get UIDs in batches
loop untile end of UIDs list:
  epost to put a batch of UIDs in the history server
  efetch to retrieve info from previous post

retmax of efetch is 1/10 of declared value from NCBI

queries are 1 sec delayed, to satisfy NCBI guidelines
(more than what they request)
"""
import argparse
import httplib
import logging
import re
import sys
import time
import urllib
import urllib2


class QueryException(Exception):
    pass


class Eutils:

    def __init__(self, options, logger):
        """
        Initialize retrieval parameters
        """
        self.logger = logger
        self.base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        self.query_string = options.query_string
        self.dbname = options.dbname
        if options.outname:
            self.outname = options.outname
        else:
            self.outname = 'NCBI_download' + '.' + self.dbname + '.fasta'
        self.ids = []
        self.retmax_esearch = 100000
        self.retmax_efetch = 500
        self.count = 0
        self.webenv = ""
        self.query_key = ""
        if options.get_uids:
            self.get_uids = True
        else:
            self.get_uids = False
        if options.iuds_file:
            with open(options.iuds_file, 'r') as f:
                self.ids.extend(f.readline().split(' '))

    def dry_run(self):
        self.get_count_value()

    def retrieve(self):
        """
        Retrieve the fasta sequences corresponding to the query
        """
        if len(self.ids) == 0:
            self.get_count_value()
        else:
            self.count = len(self.ids)
        # If no UIDs are found exit script
        if self.count > 0:
            if len(self.ids) == 0:
                self.get_uids_list()
            if not self.get_uids:
                try:
                    self.get_sequences()
                except QueryException as e:
                    self.logger.error("Exiting script.")
                    raise e
            else:
                with open(self.outname, 'w') as f:
                    f.write('\t'.join(self.ids)+'\n')
        else:
            self.logger.info("No UIDs were found. Exiting script.")

    def get_count_value(self):
        """
        just to retrieve Count (number of UIDs)
        Total number of UIDs from the retrieved set to be shown in the XML
        output (default=20). By default, ESearch only includes the first 20
        UIDs retrieved in the XML output. If usehistory is set to 'y',
        the remainder of the retrieved set will be stored on the History server

        http://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.EFetch
        """
        self.logger.info("retrieving data from %s" % self.base)
        self.logger.info("for Query: %s and database: %s" %
                         (self.query_string, self.dbname))
        querylog = self.esearch(self.dbname, self.query_string, '', '',
                                "count")
        self.logger.debug("Query response:")
        for line in querylog:
            self.logger.debug(line.rstrip())
            if '</Count>' in line:
                self.count = int(line[line.find('<Count>')+len('<Count>'):
                                 line.find('</Count>')])
        self.logger.info("Found %d UIDs" % self.count)

    def get_uids_list(self):
        """
        Increasing retmax allows more of the retrieved UIDs to be included in
        the XML output, up to a maximum of 100,000 records.
        from http://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.ESearch
        """
        retmax = self.retmax_esearch
        if (self.count > retmax):
            num_batches = (self.count / retmax) + 1
        else:
            num_batches = 1
        self.logger.info("Batch size for esearch action: %d UIDs" % retmax)
        self.logger.info("Number of batches for esearch action: %d " %
                         num_batches)
        for n in range(num_batches):
            querylog = self.esearch(self.dbname, self.query_string, n*retmax,
                                    retmax, '')
            for line in querylog:
                if '<Id>' in line and '</Id>' in line:
                    uid = (line[line.find('<Id>')+len('<Id>'):
                           line.find('</Id>')])
                    self.ids.append(uid)
            self.logger.info("Retrieved %d UIDs" % len(self.ids))

    def esearch(self, db, term, retstart, retmax, rettype):
        url = self.base + "esearch.fcgi"
        self.logger.debug("url: %s" % url)
        values = {'db': db,
                  'term': term,
                  'rettype': rettype,
                  'retstart': retstart,
                  'retmax': retmax}
        data = urllib.urlencode(values)
        self.logger.debug("data: %s" % str(data))
        req = urllib2.Request(url, data)
        response = urllib2.urlopen(req)
        querylog = response.readlines()
        response.close()
        time.sleep(1)
        return querylog

    def sanitiser(self, db, fastaseq):
        if(db not in "nuccore protein"):
            return fastaseq
        regex = re.compile(r"[ACDEFGHIKLMNPQRSTVWYBZ]{49,}")
        sane_seqlist = []
        seqlist = fastaseq.split("\n\n")
        for seq in seqlist[:-1]:
            fastalines = seq.split("\n")
            if len(fastalines) < 2:
                self.logger.info("Empty sequence for %s" %
                                 ("|".join(fastalines[0].split("|")[:4])))
                self.logger.info("%s download is skipped" %
                                 ("|".join(fastalines[0].split("|")[:4])))
                continue
            if db == "nuccore":
                badnuc = 0
                for nucleotide in fastalines[1]:
                    if nucleotide not in "ATGC":
                        badnuc += 1
                if float(badnuc)/len(fastalines[1]) > 0.4:
                    self.logger.info("%s ambiguous nucleotides in %s\
                                     or download interrupted at this offset\
                                     | %s" % (float(badnuc)/len(fastalines[1]),
                                              "|".join(fastalines[0].split("|")
                                                       [:4]),
                                              fastalines[1]))
                    self.logger.info("%s download is skipped" %
                                     (fastalines[0].split("|")[:4]))
                    continue
                """ remove spaces and trim the header to 100 chars """
                fastalines[0] = fastalines[0].replace(" ", "_")[:100]
                cleanseq = "\n".join(fastalines)
                sane_seqlist.append(cleanseq)
            elif db == "protein":
                fastalines[0] = fastalines[0][0:100]
                fastalines[0] = fastalines[0].replace(" ", "_")
                fastalines[0] = fastalines[0].replace("[", "_")
                fastalines[0] = fastalines[0].replace("]", "_")
                fastalines[0] = fastalines[0].replace("=", "_")
                """ because blast makedb doesn't like it """
                fastalines[0] = fastalines[0].rstrip("_")
                fastalines[0] = re.sub(regex, "_", fastalines[0])
                cleanseq = "\n".join(fastalines)
                sane_seqlist.append(cleanseq)
        self.logger.info("clean sequences appended: %d" % (len(sane_seqlist)))
        return "\n".join(sane_seqlist)

    def efetch(self, db, uid_list):
        url = self.base + "efetch.fcgi"
        self.logger.debug("url_efetch: %s" % url)
        values = {'db': db,
                  'id': uid_list,
                  'rettype': "fasta",
                  'retmode': "text"}
        data = urllib.urlencode(values)
        req = urllib2.Request(url, data)
        self.logger.debug("data: %s" % str(data))
        serverTransaction = False
        counter = 0
        response_code = 0
        while not serverTransaction:
            counter += 1
            self.logger.info("Server Transaction Trial:  %s" % (counter))
            try:
                self.logger.debug("Going to open")
                response = urllib2.urlopen(req)
                self.logger.debug("Going to get code")
                response_code = response.getcode()
                self.logger.debug("Going to read, de code was : %s",
                                  str(response_code))
                fasta = response.read()
                self.logger.debug("Did all that")
                response.close()
                if((response_code != 200) or
                   ("Resource temporarily unavailable" in fasta) or
                   ("Error" in fasta) or (not fasta.startswith(">"))):
                    serverTransaction = False
                    if (response_code != 200):
                        self.logger.info("urlopen error: Response code is not\
                                         200")
                    elif ("Resource temporarily unavailable" in fasta):
                        self.logger.info("Ressource temporarily unavailable")
                    elif ("Error" in fasta):
                        self.logger.info("Error in fasta")
                    else:
                        self.logger.info("Fasta doesn't start with '>'")
                else:
                    serverTransaction = True
            except urllib2.HTTPError as e:
                serverTransaction = False
                self.logger.info("urlopen error:%s, %s" % (e.code, e.read()))
            except urllib2.URLError as e:
                serverTransaction = False
                self.logger.info("urlopen error: Failed to reach a server")
                self.logger.info("Reason :%s" % (e.reason))
            except httplib.IncompleteRead as e:
                serverTransaction = False
                self.logger.info("IncompleteRead error:  %s" % (e.partial))
            if (counter > 500):
                serverTransaction = True
        if (counter > 500):
            raise QueryException({"message":
                                  "500 Server Transaction Trials attempted for\
                                  this batch. Aborting."})
        fasta = self.sanitiser(self.dbname, fasta)
        time.sleep(0.1)
        return fasta

    def get_sequences(self):
        batch_size = 200
        count = self.count
        uids_list = self.ids
        self.logger.info("Batch size for efetch action: %d" % batch_size)
        self.logger.info("Number of batches for efetch action: %d" %
                         ((count / batch_size) + 1))
        with open(self.outname, 'w') as out:
            for start in range(0, count, batch_size):
                end = min(count, start+batch_size)
                batch = uids_list[start:end]
                self.logger.info("retrieving batch %d" %
                                 ((start / batch_size) + 1))
                try:
                    mfasta = self.efetch(self.dbname, ','.join(batch))
                    out.write(mfasta + '\n')
                except QueryException as e:
                    self.logger.error("%s" % e.message)
                    raise e
        urllib.urlcleanup()


LOG_FORMAT = '%(asctime)s|%(levelname)-8s|%(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']


def command_parse():
    parser = argparse.ArgumentParser(description='Retrieve data from NCBI')
    parser.add_argument('-i', dest='query_string', help='NCBI Query String')
    parser.add_argument('--UID_list', dest='iuds_file',
                        help='file containing a list of iuds to be fetched')
    parser.add_argument('-o', dest='outname', help='output file name')
    parser.add_argument('-d', dest='dbname', help='database type')
    parser.add_argument('--count', '-c', dest='count_ids',
                        action='store_true', default=False,
                        help='dry run ouputing only the number of sequences\
                        found')
    parser.add_argument('--get_uids', '-u', dest='get_uids', default=False,
                        action='store_true', help='prints to the output a list\
                        of UIDs')
    parser.add_argument('-l', '--logfile', help='log file (default=stderr)')
    parser.add_argument('--loglevel', choices=LOG_LEVELS, default='INFO',
                        help='logging level (default: INFO)')
    args = parser.parse_args()
    if args.query_string is not None and args.iuds_file is not None:
        parser.error('Please choose either fetching the -i query or the -u\
                     list.')
    return args


def __main__():
    """ main function """
    args = command_parse()
    log_level = getattr(logging, args.loglevel)
    kwargs = {'format': LOG_FORMAT,
              'datefmt': LOG_DATEFMT,
              'level': log_level}
    if args.logfile:
        kwargs['filename'] = args.logfile
    logging.basicConfig(**kwargs)
    logger = logging.getLogger('data_from_NCBI')

    E = Eutils(args, logger)
    if args.count_ids:
        try:
            E.dry_run()
        except Exception:
            sys.exit(-1)
    else:
        try:
            E.retrieve()
        except Exception:
            sys.exit(-1)


if __name__ == "__main__":
    __main__()
