'''
	Copyright (C) 2016 Giles Miclotte (giles.miclotte@intec.ugent.be)
	This file is part of alignmentSVG.
	
	This program is free software; you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation; either version 2 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program; if not, write to the
	Free Software Foundation, Inc.,
	59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
'''

from util import *

def main_XMAP(argv=None):
	if argv == None:
		argv = sys.argv
	if (len(argv) < 9) or (len(argv) % 2 == 0):
		print('Usage: alignmentSVG.py XMAP reference.cmap ref_id ref_begin_idx ref_distance tracks.txt 1.xmap 1.bnx <2.xmap 2.bnx ...>')
		exit()
	ref_id = int(argv[3])
	SVG = SVG_properties(argv[1], int(argv[4]), int(argv[5])) #130 * 1000 * 1000, 100 * 1000
	eprint('Parsing files.')
	cmap = cmap_parse(argv[2])
	with open(argv[6]) as f:
		tracks = f.readlines()
	tracks = ['Real data', 'Simulation'] #TODO remove this line
	for i in range(7, len(argv), 2):
		xmaps += [xmap_parse(argv[i])]
		bnxs += [bnx_parse(argv[i + 1])]
	print(make_svg(SVG, cmap[ref_id], [xmap[ref_id] for xmap in xmaps], bnxs, tracks))

def main_SAM(argv=None):
	if argv == None:
		argv = sys.argv
	if len(argv) < 6:
		print('Usage: alignmentSVG.py SAM reference.fasta ref_id ref_begin_idx ref_distance sorted.sam reads1.fastq <reads2.fastq ...>')
		exit()
	#specify input, can be changed to cl options of course
	reference_file = argv[2]
	ref_id = int(argv[3])
	SVG = SVG_properties(argv[1], int(argv[4]), int(argv[5]))
	sam_file = argv[6]
	read_files = [argv[i] for i in range(7, len(argv))] # this can be several files, each will create a new alignment track
	#parse input
	references = [Sequence(s[0], s[1]) for s in fasta_parse(reference_file)]
	sam_entries = sam_parse(sam_file)
	# TODO: we don't actually need to parse the fastq files right now, more efficient to save till moment of drawing that track
	reads = []
	for i in range(len(read_files)):
		fasta = {}
		for s in fastq_parse(read_files[i]):
			sequence = Sequence(s[0], s[1])
			fasta[sequence.name] = sequence
		reads += [fasta]
	tracks = ['Initial reads', 'Corrected reads'] #TODO remove this line
	print(make_svg(SVG, references[ref_id], sam_entries, reads, tracks))

def main(argv=None):
	if argv == None:
		argv = sys.argv
	if len(argv) < 2:
		print('Usage: alignmentSVG.py [SAM|XMAP]')
		exit()
	if argv[1] == 'SAM':
		main_SAM(argv)
	elif argv[1] == 'XMAP':
		main_XMAP(argv)
	else:
		print('Usage: alignmentSVG.py [SAM|XMAP]')

main()