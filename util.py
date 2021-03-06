'''
	Copyright (C) 2016 Giles Miclotte (giles.miclotte@intec.ugent.be)
	This file is part of alignmentSVG.

	This program is free software; you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation; either version 2 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program; if not, write to the
	Free Software Foundation, Inc.,
	59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
'''

from __future__ import print_function
import sys
import re

from align import NW

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

class SAMEntry:
	def __init__(self, props):
		self.qname = props[0]
		self.flag = props[1]
		self.rname = props[2]
		self.pos = int(props[3]) - 1 #change to 0-based
		self.mapq = props[4]
		self.cigar = re.findall(r'(\d+)([A-Z]{1})', props[5])
		self.cigar = [(int(c), s) for c, s in self.cigar]
		self.rnext = props[6]
		self.pnext = props[7]
		self.tlen = props[8]
		self.seq = props[9]
		self.qual = props[10]
		self.optional = {}
		for i in range(11, len(props)):
			field = props[i].split(':')
			if field[1] == 'i':
				field[2] = int(field[2])
			elif field[1] == 'f':
				field[2] = float(field[2])
			self.optional[field[0]] = [field[1], field[2]]
		self.len = len(self.seq)
		if self.cigar[0][1] == 'S':
			self.len -= self.cigar[0][0]
		if self.cigar[-1][1] == 'S':
			self.len -= self.cigar[-1][0]

class Sequence:
	def __init__(self, meta, seq):
		self.meta = meta
		self.name = meta.strip().split('\t')[0].split(' ')[0]
		self.seq = seq


class XmapEntry:
	def __init__(self):
		self.Alignment = []

	def set_props(self, line):
		props = line.strip().split('\t')
		self.XmapEntryID = int(props[0]) - 1
		self.QryContigID = int(props[1]) - 1
		self.RefContigID = int(props[2]) - 1
		self.QryStartPos = float(props[3])
		self.QryEndPos = float(props[4])
		self.RefStartPos = float(props[5])
		self.RefEndPos = float(props[6])
		self.Orientation = props[7] == '+'
		self.Confidence = float(props[8])
		self.HitEnum = props[9]
		self.QryLen = float(props[10])
		self.RefLen = float(props[11])
		self.LabelChannel = props[12]
		for a in props[13][1:-1].split(')('):
			self.Alignment += [a.split(',')]

def ltkmer_parse(ifname):
	infile = open(ifname)
	for line in infile:
		l = line.split('\t')
		if l[1] != '0':
			yield int(l[0])
	infile.close()

def fasta_parse(ifname):
	infile = open(ifname)
	meta = ''
	seq = ''
	for line in infile:
		if line.startswith('>'): #header
			if len(meta) > 0:
				yield [meta, seq]
				meta = ''
				seq = ''
			meta = line[1:]
		else:
			seq += line.strip()
	if len(meta) > 0:
		yield [meta, seq]
	infile.close()

def fastq_parse(ifname):
	infile = open(ifname)
	meta = ''
	seq = ''
	count = 0
	for line in infile:
		if count == 0:
			if len(meta) > 0:
				yield [meta, seq]
				meta = ''
				seq = ''
			meta = line[1:]
		elif count == 1:
			seq = line.strip()
		count = (count + 1) % 4
	if len(meta) > 0:
		yield [meta, seq]
	infile.close()

def sam_parse(ifname):
	infile = open(ifname)
	sam = []
	for line in infile:
		if line.startswith('@'): #header
			continue
		else: #entry
			props = line.strip().split('\t')
			if props[5] != '*':
				sam += [SAMEntry(props)]
	infile.close()
	return sam

def cmap_parse(ifname):
	infile = open(ifname)
	cmap = []
	for line in infile:
		if line.startswith('#'):
			continue
		else:
			cmap_entry = line.strip().split('\t')
			refcontigID = int(cmap_entry[0])
			while refcontigID > len(cmap):
				cmap += [[]]
			cmap[refcontigID - 1] += [float(cmap_entry[5])]
	return cmap

def xmap_parse(ifname):
	infile = open(ifname)
	xmap = []
	for line in infile:
		if line.startswith('#'):
			continue
		else:
			entry = XmapEntry()
			entry.set_props(line)
			while entry.RefContigID + 1 > len(xmap):
				xmap += [[]]
			xmap[entry.RefContigID] += [entry]
	return xmap

def bnx_parse(ifname):
	infile = open(ifname)
	bnx = {}
	ID=-1
	for line in infile:
		if line.startswith('#'):
			continue
		if line.startswith('0'):
			ID = int(line.strip().split('\t')[1]) - 1
			continue
		if line.startswith('1'):
			bnx[ID] = line.strip().split('\t')[1:]
		if line.startswith('Q'):
			continue
	return bnx

def entry_before(SVG, ref, entry):
	if SVG.type == 'SAM':
		entry_end = entry.pos + entry.len
		ref_start = ref.pos
		return entry_end + SVG.min_separation < ref_start
	if SVG.type == 'XMAP':
		entry_end = entry.RefEndPos + entry.QryLen - entry.QryEndPos
		ref_start = -ref.QryStartPos + ref.RefStartPos
		return entry_end + SVG.min_separation < ref_start

def entry_after(SVG, ref, entry):
	return entry_before(SVG, entry, ref)

def pile_end_entries(SVG, piles, entry):
	for i in range(len(piles)):
		if entry_after(SVG, piles[i][-1], entry):
			#append entry
			piles[i] += [entry]
			return
	#make new pile
	piles += [[entry]]
	return

def pile_entries(SVG, entries):
	piles = []
	if SVG.type == 'SAM':
		for entry in entries:
			if entry.pos < SVG.begin + SVG.dist and SVG.begin < entry.pos + entry.len:
				pile_end_entries(SVG, piles, entry)
	elif SVG.type == 'XMAP':
		for entry in entries:
			if entry.Orientation and entry.RefStartPos < SVG.begin + SVG.dist * (1.0 - SVG.min_overlap) and SVG.begin + SVG.dist * SVG.min_overlap < entry.RefEndPos:
				pile_end_entries(SVG, piles, entry)
	return piles

class SVG_properties:
	def __init__(self, data_type, begin, dist, text):
		# zoom location
		self.begin = begin
		self.dist = dist
		# colours
		self.reference_colour = '#b2df8a'
		self.line_colour = ['#a6cee3', '#b2df8a']
		self.nick_colour = '#33a02c'
		self.label_colour = '#ff0000'
		self.label2_colour = '#0000ff'
		self.background_style = '\"fill:white;fill-opacity:1.0;\"'
		self.text_style = '\"writing-mode: bt;text-anchor: middle\"'
		self.ltkmer_style = '\"fill-opacity:0.0;stroke-width:1;stroke:black\" id=\"ltkmer\"'
		# [current|max] height of the picture
		self.depth = 0
		self.height = 3000
		# draw text or not
		self.text = text
		# image borders
		self.base_border = 1
		self.border = {	'left' : self.base_border,
				'lefttext' : self.base_border,
				'right' : self.base_border,
				'top' : self.base_border,
				'toptext' : self.base_border,
				'bottom' : self.base_border
		}
		# data type specific settings
		self.type = data_type.upper()
		if self.type == 'SAM':
			self.init_sam()
		elif self.type == 'XMAP':
			self.init_xmap()
		else:
			eprint('Unsupported data type:' + self.type)
			exit()

	def init_sam(self):
		self.max_subtracks = 200
		self.border = {	'left' : 20.5,
				'lefttext' : 15,
				'right' : 26,
				'top' : 0,
				'toptext' : self.base_border,
				'bottom' : 10
		}
		self.min_separation = 5
		self.block_size = 12.55
		self.font_size = self.block_size * 1.2
		self.hshift_size = self.block_size * 0.5
		self.vshift_size = self.block_size * 0.9
		self.line_height = self.block_size
		self.view_range = [self.begin, self.begin + self.dist]
		self.track_distance = 10
		self.line_distance = 1
		if self.text:
			self.border['top'] += 6 * self.block_size
			self.border['toptext'] -= 3 * self.block_size
			self.text_shift = -self.block_size
			self.zoom = 1 / self.block_size
			self.reference_height = self.line_height
			self.ref_loc_nr = 5

	def init_xmap(self):
		self.max_subtracks = 20
		self.min_separation = 1000
		self.zoom = 100
		self.nick_width = 2
		self.view_range = [self.begin, self.begin + self.dist]
		self.min_overlap = 1
		self.text_shift = 6
		self.reference_height = 20
		self.track_distance = 10
		self.line_height = 6
		self.line_distance = 2
		self.ref_loc_nr = 3
		self.font_size = 8

	def track_style(self, colour):
		return '\"fill:' + colour + ';stroke:black;stroke-width:0;fill-opacity:1.0;stroke-opacity:1.0\"'

def add_svg_rect(SVG, x, y, width, height, style):
	return '\n' + '<rect x=\"' + str(x) + '\" y=\"' + str(y) + '\" width=\"' + str(width) + '\" height=\"' + str(height) + '\" style=' + str(style) + '/>'

def add_svg_empty_space(SVG, distance):
	SVG.depth += distance

def draw_ref_seq(SVG, x, y, ref, seq, start, cigar):
	svg = '<g transform=\"translate(' + str(SVG.hshift_size) + ',' + str(y + SVG.vshift_size) + ')\" font-size=\"' + str(SVG.font_size) + '\" text-anchor=\"middle\">'
	ref_idx = 0
	seq_idx = start
	while seq_idx < len(seq) and ref_idx < len(ref):
		svg += '<text x=\"' + str(ref_idx * SVG.block_size) + '\" >' + str(seq[seq_idx]) + '</text>'
		ref_idx += 1
		seq_idx += 1
	svg += '</g>\n'
	return svg

def draw_acgt(SVG, x, y, c):
	return '<text x=\"' + str(x + SVG.block_size / 2) + '\" y=\"' + str(y + SVG.block_size - 1) + '\" font-size=\"' + str(SVG.font_size) + '\" text-anchor=\"middle\" alignment-baseline=\"middle\">' + str(c) + '</text>'

def add_nicks(SVG, cmap, y, h):
	svg = ''
	for nick in cmap:
		if nick < SVG.view_range[0]:
			continue
		if nick > SVG.view_range[1]:
			break
		x = SVG.border['left'] + (nick - SVG.begin - SVG.zoom / 2) / SVG.zoom
		w = SVG.nick_width
		svg += add_svg_rect(SVG, x, y, w, h, SVG.track_style(SVG.nick_colour))
		update_depth(SVG, y, h)
		#svg += '<g writing-mode=\"tb-rl\" fill=\"black\" font-size=\"4\" transform=\"translate(' + str(x) + ')\"> <text y=\"0px\">' + str(nick) + ' ' + str(x) + '</text></g>'
	return svg

def xmap_partial_svg(SVG, cmap, bnx, piles, max_subtracks, track_names, track):
	eprint('Drawing track: ' + track_names[track] + '.')
	svg = ''
	add_svg_empty_space(SVG, SVG.track_distance)
	subtracks = 0
	for pile in piles:
		subtracks += 1
		y = SVG.depth
		h = SVG.line_height
		for e in pile:
			if not e.Orientation:
				continue
			start = -e.QryStartPos + e.RefStartPos - SVG.begin
			trimmed_start = SVG.border['left'] + max(0, start / SVG.zoom)
			end = e.RefEndPos - SVG.begin + e.QryLen - e.QryEndPos
			trimmed_end = SVG.border['left'] + min(end / SVG.zoom, SVG.dist / SVG.zoom)
			svg += '\n'
			x = trimmed_start
			w = trimmed_end - trimmed_start
			svg += add_svg_rect(SVG, x, y, w , h, SVG.track_style(SVG.line_colour[track]))
			update_depth(SVG, y, h)
			svg += add_nicks(SVG, [cmap[int(nick)] for nick, label in e.Alignment], y, h)
			'''
			for nick, label in e.Alignment:
				location = (cmap[int(nick) - 1] - SVG.begin - SVG.zoom / 2) / SVG.zoom
				if (SVG.border['left'] < location and location < SVG.dist / SVG.zoom + SVG.border['left']):
					x = SVG.border['left'] + location
					w = SVG.nick_width
					svg += add_svg_rect(SVG, x, y, w , h, SVG.track_style(SVG.nick_colour))
			for label in bnx[e.QryContigID]:
				if e.Orientation:
					location = (float(label) + start - SVG.zoom / 2) / SVG.zoom
					if (SVG.border_distance < location and location < SVG.dist / SVG.zoom + 3 * SVG.border_distance):
						x = 2 * SVG.border_distance + location
						w = SVG.nick_width
						svg += add_svg_rect(SVG, x, y + h / 2, w , h / 2, SVG.track_style(SVG.label_colour))
				else:
					label = float(bnx[e.QryContigID][-1]) - float(label)
					location = (end - float(label) - SVG.zoom / 2) / SVG.zoom
					if (SVG.border_distance < location and location < SVG.dist / SVG.zoom + 3 * SVG.border_distance):
						x = 2 * SVG.border_distance + location
						w = SVG.nick_width
						svg += add_svg_rect(SVG, x, y + h / 2, w , h / 2, SVG.track_style(SVG.label2_colour))
			'''
		add_svg_empty_space(SVG, SVG.line_distance)
		if subtracks == max_subtracks:
			break
	#correct for depth after last subtrack
	add_svg_empty_space(SVG, -SVG.line_distance)
	if SVG.text:
		#track string
		svg += '\n' + '<g writing-mode=\"tb-rl\" fill=\"black\" font-size=\"8\">'
		x = SVG.border['lefttext']
		y = SVG.depth - (subtracks * (SVG.line_distance + SVG.line_height) - SVG.line_distance) / 2
		svg += '\n' + '<text transform=\"translate(' + str(x) + ', ' + str(y) + ')rotate(270)\" style=' + SVG.text_style + '>' + tracks[track] + '</text>'
		svg += '\n</g>'
	return svg

def draw_seq(SVG, x, y, ref, seq, cigar, diff_only = True):
	svg = '<g transform=\"translate(' + str(0) + ', ' + str(SVG.vshift_size) + ')\" font-size=\"' + str(SVG.font_size) + '\" text-anchor=\"middle\">'
	ref_idx = 0
	seq_idx = 0
	cig_idx = 0
	cig_count = 0
	# expanded cigar
	e_cigar = ''.join(c[1] * c[0] for c in cigar if c[1] != 'S' and c[1] != 'H')
	for c in e_cigar:
		if c == 'D':
			xp = x + ref_idx * SVG.block_size
			if SVG.border['left'] <= xp and xp < SVG.border['left'] + SVG.dist * SVG.block_size:
				svg += '<text x=\"' + str(xp + SVG.block_size / 2) + '\">-</text>'
			ref_idx += 1
		elif c == 'I':
			xp = x + ref_idx * SVG.block_size - 1
			if SVG.border['left'] <= xp and xp < SVG.border['left'] + SVG.dist * SVG.block_size:
				svg += '<rect x=\"' + str(xp) + '\" y=\"' + str(-SVG.vshift_size) + '\" width=\"' + str(2) + '\" height=\"' + str(SVG.block_size) + '\" style=' + SVG.track_style(SVG.label_colour) + '/>'
			seq_idx += 1
		elif c == 'M':
			xp = x + ref_idx * SVG.block_size
			if SVG.border['left'] <= xp and xp < SVG.border['left'] + SVG.dist * SVG.block_size:
				#eprint(seq_idx, ref_idx, seq[seq_idx], ref[ref_idx])
				if (not diff_only) or seq[seq_idx] != ref[ref_idx]:
					svg += '<text x=\"' + str(xp + SVG.block_size / 2) + '\">' + str(seq[seq_idx]) + '</text>'
			ref_idx += 1
			seq_idx += 1
	svg += '</g>\n'
	return svg

def update_depth(SVG, y, h):
	SVG.depth = y + h if y + h > SVG.depth else SVG.depth

def fasta_partial_svg(SVG, ref, fasta, piles, max_subtracks, track_names, track, extra):
	eprint('Drawing track: ' + track_names[track] + '.')
	svg = ''
	add_svg_empty_space(SVG, SVG.track_distance)
	prev_depth = SVG.depth
	subtracks = 0
	svg += '<g transform=\"translate(' + str(0) + ',' + str(prev_depth) + ')\" id=\"' + track_names[track] + '\">\n'
	for pile in piles:
		subtracks += 1
		y = SVG.depth - prev_depth
		h = SVG.block_size
		for e in pile:
			rel_pos = e.pos - SVG.begin
			rel_end = rel_pos + e.len
			x = SVG.border['left'] + max(rel_pos, 0) * SVG.block_size
			w = SVG.border['left'] + min(rel_end, SVG.dist) * SVG.block_size - x
			svg += '\n'
			svg += '<g transform=\"translate(' + str(0) + ',' + str(y) + ')\">\n'
			svg += add_svg_rect(SVG, x, 0, w , h, SVG.track_style(SVG.line_colour[track%2]))
			update_depth(SVG, prev_depth + y, h)
			ref_start = SVG.view_range[0] + rel_pos
			ref_end = SVG.view_range[0] + rel_pos + e.len
			ref_substr = ref.seq[ref_start:]
			seq = fasta[e.qname].seq
			if e.cigar[0][1] == 'S' or  e.cigar[0][1] == 'H':
				seq = seq[e.cigar[0][0]:]
			if e.cigar[-1][1] == 'S' or  e.cigar[-1][1] == 'H':
				seq = seq[:len(seq) - e.cigar[-1][0]]
			cigar = e.cigar
			if track != extra['sam_track']:
				ins = sum(i for (i,j) in e.cigar if j == 'I')
				cigar = NW(ref_substr[:len(seq) - ins], seq)
			eprint(e.qname, ''.join(str(i)+str(j) for (i,j) in cigar))
			svg += draw_seq(SVG, SVG.border['left'] + rel_pos * SVG.block_size, 0, ref_substr, seq, cigar)
			svg += '</g>\n'
		add_svg_empty_space(SVG, SVG.line_distance)
		if subtracks == max_subtracks:
			break
	#correct for depth after last subtrack
	add_svg_empty_space(SVG, -SVG.line_distance)
	svg += "<g transform=\"translate(" + str(SVG.border['lefttext']) + "," + str((SVG.depth - prev_depth) / 2) + ") rotate(270)\" style=\"stroke:none; fill:black; font-family:Arial; font-size:" + str(SVG.font_size) + "pt; text-anchor:middle\"> <text>" + track_names[track] + "</text> </g>"
	svg += ltkmer_partial_svg(SVG, track, SVG.depth - prev_depth)
	svg += '</g>\n'
	return svg

def reference_partial_svg(SVG, ref, extra):
	if SVG.type == 'SAM':
		return reference_partial_svg_sam(SVG, ref, extra)
	elif SVG.type == 'XMAP':
		return reference_partial_svg_xmap(SVG, ref)

def reference_location(SVG):
	svg = '\n' + '<g writing-mode=\"tb-rl\" fill=\"black\" font-size=\"' + str(SVG.font_size) + '\">'
	nr = SVG.ref_loc_nr
	for i in range(nr):
		#positions
		if SVG.type == 'SAM':
			text = str(int((SVG.begin + i * (SVG.dist - 1) / (nr - 1)))) + 'bp'
		elif SVG.type == 'XMAP':
			text = str(int((SVG.begin + i * (SVG.dist - 1) / (nr - 1)) / 1000)) + 'kbp'
		x = SVG.text_shift + SVG.border['left'] + i * ((SVG.dist - 2) / SVG.zoom - SVG.text_shift) / (nr - 1)
		y = SVG.border['toptext']
		svg += '\n' + '<text transform=\"translate(' + str(x) + ', ' + str(y) + ')rotate(270)\" style=' + SVG.text_style + '>' + text + '</text>'
	svg += '\n</g>'
	#reference string
	svg += '\n' + '<g writing-mode=\"tb-rl\" fill=\"black\" font-size=\"8\">'
	x = SVG.border['lefttext']
	y = SVG.border['top'] + SVG.reference_height / 2
	svg += '\n' + '<text transform=\"translate(' + str(x) + ', ' + str(y) + ')rotate(270)\" style=' + SVG.text_style + '>Ref</text>'
	svg += '\n</g>'
	return svg

def reference_partial_svg_sam(SVG, ref, extra):
	eprint('Drawing reference track.')
	if len(ref.seq) < SVG.view_range[1]:
		SVG.dist = len(ref.seq) - SVG.begin
		SVG.view_range = [SVG.begin, len(ref.seq)]
	x = SVG.border['left']
	y = SVG.border['top']
	w = SVG.dist * SVG.block_size
	h = SVG.block_size
	svg = '<g transform=\"translate(' + str(x) + ',' + str(y) + ')\">\n'
	if SVG.text:
		svg += reference_location(SVG)
	svg += add_svg_rect(SVG, 0, 0, w, h, SVG.track_style(SVG.reference_colour))
	update_depth(SVG, y, h)
	ref_substr = ref.seq[SVG.view_range[0]:SVG.view_range[1]]
	svg += draw_ref_seq(SVG, 0, 0, ref_substr, ref_substr, 0, SVG.track_style(SVG.reference_colour))
	for contig in extra['contigs']:
		for idx in [0, 1]:
			if SVG.view_range[0] < contig[idx] and contig[idx] < SVG.view_range[1]:
				x = (contig[idx] - SVG.view_range[0] + 1) * SVG.block_size - 1
				svg += add_svg_rect(SVG, x, 0, 2, SVG.block_size, SVG.track_style(SVG.label_colour))
				if idx == 1:
					x = x + 1 - SVG.block_size / 2
				svg += add_svg_rect(SVG, x, -2, SVG.block_size / 2 + 1, 2, SVG.track_style(SVG.label_colour))
				svg += add_svg_rect(SVG, x, SVG.block_size, SVG.block_size / 2 + 1, 2, SVG.track_style(SVG.label_colour))
				eprint(contig[idx])
	svg += '</g>\n'
	svg += "<g transform=\"translate(" + str(SVG.border['lefttext']) + "," + str((SVG.border['top'] + SVG.depth) / 2) + ") rotate(270)\" style=\"stroke:none; fill:black; font-family:Arial; font-size:" + str(SVG.font_size) + "pt; text-anchor:middle\"> <text>Ref</text> </g>"
	return svg

def reference_partial_svg_xmap(SVG, ref):
	eprint('Drawing reference track.')
	if ref[-1] < SVG.view_range[1]:
		SVG.dist = ref[-1] - SVG.begin
		SVG.view_range = [SVG.begin, ref[-1]]
	svg = ''
	if SVG.text:
		reference_location(SVG)
	x = SVG.border['left']
	y = SVG.border['top']
	w = SVG.dist / SVG.zoom
	h = SVG.reference_height
	svg += add_svg_rect(SVG, x, y, w, h, SVG.track_style(SVG.reference_colour))
	update_depth(SVG, y, h)
	svg += add_nicks(SVG, ref, y, SVG.reference_height)
	return svg

def ltkmer_rect(SVG, position, length, h):
	x = SVG.border['left'] + (position - SVG.begin) * SVG.block_size
	w = length * SVG.block_size
	wmax = SVG.border['left'] + SVG.dist * SVG.block_size - x
	eprint(w, wmax)
	w = w if w < wmax else wmax
	svg = add_svg_rect(SVG, x, 0, w, h, SVG.ltkmer_style)
	return svg

def ltkmer_partial_svg(SVG, track, h):
	if SVG.kmer_count[track] == '-':
		return ''
	svg = ''
	begin = -1
	end = begin
	for pos in ltkmer_parse(SVG.kmer_count[track]):
		if end < pos:
			if begin > 0:
				svg += ltkmer_rect(SVG, begin, end - begin, h)
			begin = pos
		end = pos + 21
	svg += ltkmer_rect(SVG, begin, end - begin, h)
	return svg

def make_svg(SVG, ref, alnms, tracks, track_names, extra = {'sam_track' : -1}):
	svg = reference_partial_svg(SVG, ref, extra)
	ref_depth = SVG.depth
	# max total - used - bottom border - track borders
	remaining_depth = SVG.height - SVG.depth - SVG.border['bottom'] - len(tracks) * SVG.track_distance
	max_subtracks = (remaining_depth + len(tracks) * SVG.line_distance) / (SVG.line_height + SVG.line_distance)
	max_subtracks = max_subtracks if max_subtracks < SVG.max_subtracks else SVG.max_subtracks
	if extra['filter']:
		filtered_alnms = []
		filtered = 0
		for alnm in alnms:
			name = alnm.qname
			baseline = tracks[0][name].seq
			filter = True
			for i in range(1, len(tracks)):
				if tracks[i][name].seq != baseline:
					filter = False
			if not filter:
				filtered_alnms += [alnm]
			else:
				filtered += 1
		eprint('Filtered ', filtered, ' unchanged reads.')
		alnms = filtered_alnms
	if SVG.type == 'SAM':
		piles = pile_entries(SVG, alnms)
	for i in range(len(tracks)):
		track = tracks[i]
		if SVG.type == 'SAM':
			svg += fasta_partial_svg(SVG, ref, track, piles, max_subtracks, track_names, i, extra)
		elif SVG.type == 'XMAP':
			piles = pile_entries(SVG, alnms[i])
			svg += xmap_partial_svg(SVG, ref, track, piles, max_subtracks, track_names, i)
	SVG.height = SVG.depth + SVG.border['bottom']
	return start_partial_svg(SVG) + svg + end_partial_svg()

def start_partial_svg(SVG):
	if SVG.type == 'SAM':
		w = SVG.dist * SVG.block_size + SVG.border['left'] + SVG.border['right']
	elif SVG.type == 'XMAP':
		w = SVG.dist / SVG.zoom + SVG.border['left'] + SVG.border['right']
	h = SVG.height
	svg = '<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"no\"?>'
	svg += '<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\" \"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\">'
	svg += '<svg viewBox=\"0 0 ' + str(w) + ' ' + str(h) + '\"'
	svg += ' xmlns=\"http://www.w3.org/2000/svg\"'
	svg += ' xmlns:xlink=\"http://www.w3.org/1999/xlink\"'
	svg += '>\n'
	svg += '<rect x=\"0\" y=\"0\" width=\"110%\" height=\"110%\" style=' + SVG.background_style + '/>\n'
	svg += '<g transform=\"translate(0,0)\" id=\"fullSVG\">'
	svg += '<g transform=\"translate(0,0)\" id=\"alignmentSVG\">\n'
	return svg

def end_partial_svg():
	svg = '</g>\n'
	svg += '</g>\n'
	svg += '</svg>'
	return svg
