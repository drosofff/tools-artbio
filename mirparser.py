#!/usr/bin/python
# python parser module for pipeline for miRNA full profiling with bowtie 10/10/2011
# version 3 (22-4-2014)
# Usage miRNA_bowtie_profiler.py <bowtie_out> <bowtie miRNA index !remove> <LABEL> <output1 file> <output2 file> <bowtie miRNA index change ranking> <option tag>

import sys, re, os, subprocess, shlex, datetime, time
from collections import defaultdict
from smRtools import *

class recursivedefaultdict(defaultdict):
  def __init__(self):
    self.default_factory = type(self)

def bowtie_output_analysis(bowtie_output, miR_sequence_liste, label, analysis_output, flat_hit_list):
  super_hash = recursivedefaultdict() # miR -> offset -> size -> occurence, The super hash which contains all the data
  crude_occurence = defaultdict(int)
  REPORT  = open(analysis_output, "w") # think to close
  for line in open(bowtie_output):
    fields = line.rstrip().split() # 21-2-2013: removed "\t" argument from the split() method
    target_name, target_offset, read_sequence= fields[1], int(fields[2])+1, fields[3] #0-based bowtie offset transformed in 1-based offset
    size =  len(read_sequence)
    try: super_hash[target_name][target_offset][size] += 1
    except : super_hash[target_name][target_offset][size] = 1
    crude_occurence[target_name] += 1
  upstream = defaultdict(int)
  downstream = defaultdict(int)
  for miR in sorted(super_hash.keys()):
    miR_size = len(miR_sequence_liste[miR])
    upstream_counts = defaultdict(int)
    downstream_counts = defaultdict(int)
    start_shift= (miR_size//2) -15
    end_shift = (miR_size//2) +15
    for split_site in range(start_shift, end_shift):
      upstream_counts[split_site] = downstream_counts[split_site] = 0
      for offset in sorted(super_hash[miR].keys()):
        for size in sorted(super_hash[miR][offset].keys()):
          if ((offset + size +1) < split_site):
            upstream_counts[split_site] += super_hash[miR][offset][size]
          elif (offset >= split_site):
            downstream_counts[split_site] += super_hash[miR][offset][size]
    sum_count = defaultdict(int)
    reduced_prout = []
    for split_site in sorted(upstream_counts.keys()):
      sum_count[split_site] = upstream_counts[split_site] + downstream_counts[split_site]
    maxcount = 0
    for split_site in sorted(sum_count, key=sum_count.get, reverse=True):
      if (sum_count[split_site] >= maxcount):
        reduced_prout.append(split_site)
        maxcount = sum_count[split_site]
      else : break
    median_split = reduced_prout[len(reduced_prout)//2]
    footprint_split = "(" * median_split + ")" * (miR_size - median_split)
    s = miR + "\n" + miR_sequence_liste[miR] + "\n" + footprint_split + "\n"
    REPORT.write(s)
    for offset in sorted(super_hash[miR].keys()):
      for size in sorted(super_hash[miR][offset].keys()):
        read_sequence = miR_sequence_liste[miR][offset-1:offset-1+size]
        s = "." * (offset-1) + read_sequence + "." * (miR_size - offset +1 - size)
        s += "\t" + str(offset) + "\t" + str(super_hash[miR][offset][size]) + "\t(" + str(size) + " nt)\n"
        REPORT.write(s)
    upstream[miR] = upstream_counts[median_split]
    downstream[miR] = downstream_counts[median_split]
  s= "\n# hit table #\n#gene\tpre-miR\tmiR_5p\tmiR_3p\n"
  REPORT.write(s)
  for miR in sorted(miR_sequence_liste.keys()):
    try:
      s = miR + "\t" + str(crude_occurence[miR]) + "\t" + str(upstream[miR]) + "\t" + str(downstream[miR]) + "\n"
      REPORT.write(s)
    except:
      s = miR + "\t0\t0\t0\n"
      REPORT.write(s)
      print s
  REPORT.close()
  HITS = open (flat_hit_list, "w")
  print >> HITS, "gene\t%s" % label
  for miR in sorted(miR_sequence_liste.keys()):
    try:
      print >> HITS, "%s_5p\t%s" % (miR, str(upstream[miR]))
    except:
      print >> HITS, "%s_5p\t0" % miR
    try:
      print >> HITS, "%s_3p\t%s" % (miR, str(downstream[miR]))
    except:
      print >> HITS, "%s_3p\t0" % miR
  HITS.close()

if sys.argv[-1] == "--extract_index":
  ItemDic = get_fasta (sys.argv[-2])
else:
  ItemDic = get_fasta_from_history (sys.argv[-2])

bowtie_output_analysis(sys.argv[1], ItemDic, sys.argv[2], sys.argv[3], sys.argv[4])
