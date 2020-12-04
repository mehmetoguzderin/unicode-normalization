#!/usr/bin/env python
#
# Copyright 2011-2018 The Rust Project Developers. See the COPYRIGHT
# file at the top-level directory of this distribution and at
# http://rust-lang.org/COPYRIGHT.
#
# Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
# http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
# <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
# option. This file may not be copied, modified, or distributed
# except according to those terms.

# This script uses the following Unicode tables:
# - DerivedNormalizationProps.txt
# - NormalizationTest.txt
# - UnicodeData.txt
# - StandardizedVariants.txt
#
# Since this should not require frequent updates, we just store this
# out-of-line and check the tables.rs and normalization_tests.rs files into git.
import collections
import urllib.request

UNICODE_VERSION = "13.0.0"
UCD_URL = "https://www.unicode.org/Public/%s/ucd/" % UNICODE_VERSION

PREAMBLE = """// Copyright 2012-2018 The Rust Project Developers. See the COPYRIGHT
// file at the top-level directory of this distribution and at
// http://rust-lang.org/COPYRIGHT.
//
// Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
// http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
// <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
// option. This file may not be copied, modified, or distributed
// except according to those terms.

// NOTE: The following code was generated by "scripts/unicode.py", do not edit directly

#![allow(missing_docs)]
"""

NormalizationTest = collections.namedtuple(
    "NormalizationTest",
    ["source", "nfc", "nfd", "nfkc", "nfkd"],
)

# Mapping taken from Table 12 from:
# http://www.unicode.org/reports/tr44/#General_Category_Values
expanded_categories = {
    'Lu': ['LC', 'L'], 'Ll': ['LC', 'L'], 'Lt': ['LC', 'L'],
    'Lm': ['L'], 'Lo': ['L'],
    'Mn': ['M'], 'Mc': ['M'], 'Me': ['M'],
    'Nd': ['N'], 'Nl': ['N'], 'No': ['No'],
    'Pc': ['P'], 'Pd': ['P'], 'Ps': ['P'], 'Pe': ['P'],
    'Pi': ['P'], 'Pf': ['P'], 'Po': ['P'],
    'Sm': ['S'], 'Sc': ['S'], 'Sk': ['S'], 'So': ['S'],
    'Zs': ['Z'], 'Zl': ['Z'], 'Zp': ['Z'],
    'Cc': ['C'], 'Cf': ['C'], 'Cs': ['C'], 'Co': ['C'], 'Cn': ['C'],
}

# Constants from Unicode 9.0.0 Section 3.12 Conjoining Jamo Behavior
# http://www.unicode.org/versions/Unicode9.0.0/ch03.pdf#M9.32468.Heading.310.Combining.Jamo.Behavior
S_BASE, L_COUNT, V_COUNT, T_COUNT = 0xAC00, 19, 21, 28
S_COUNT = L_COUNT * V_COUNT * T_COUNT

class UnicodeData(object):
    def __init__(self):
        self._load_unicode_data()
        self.norm_props = self._load_norm_props()
        self.norm_tests = self._load_norm_tests()

        self.canon_comp = self._compute_canonical_comp()
        self.canon_fully_decomp, self.compat_fully_decomp = self._compute_fully_decomposed()

        self.svar_decomp = {}
        self.svar_fully_decomp = {}
        self._load_standardized_variants()

        def stats(name, table):
            count = sum(len(v) for v in table.values())
            print("%s: %d chars => %d decomposed chars" % (name, len(table), count))

        print("Decomposition table stats:")
        stats("Canonical decomp", self.canon_decomp)
        stats("Compatible decomp", self.compat_decomp)
        stats("Standardized Variants", self.svar_decomp)
        stats("Canonical fully decomp", self.canon_fully_decomp)
        stats("Compatible fully decomp", self.compat_fully_decomp)
        stats("Standardized Variants", self.svar_fully_decomp)

        self.ss_leading, self.ss_trailing = self._compute_stream_safe_tables()

    def _fetch(self, filename):
        resp = urllib.request.urlopen(UCD_URL + filename)
        return resp.read().decode('utf-8')

    def _load_unicode_data(self):
        self.name_to_char_int = {}
        self.combining_classes = {}
        self.compat_decomp = {}
        self.canon_decomp = {}
        self.general_category_mark = []

        for line in self._fetch("UnicodeData.txt").splitlines():
            # See ftp://ftp.unicode.org/Public/3.0-Update/UnicodeData-3.0.0.html
            pieces = line.split(';')
            assert len(pieces) == 15
            char, category, cc, decomp = pieces[0], pieces[2], pieces[3], pieces[5]
            char_int = int(char, 16)

            name = pieces[1].strip()
            self.name_to_char_int[name] = char_int

            if cc != '0':
                self.combining_classes[char_int] = cc

            if decomp.startswith('<'):
                self.compat_decomp[char_int] = [int(c, 16) for c in decomp.split()[1:]]
            elif decomp != '':
                self.canon_decomp[char_int] = [int(c, 16) for c in decomp.split()]

            if category == 'M' or 'M' in expanded_categories.get(category, []):
                self.general_category_mark.append(char_int)

    def _load_standardized_variants(self):
        for line in self._fetch("StandardizedVariants.txt").splitlines():
            strip_comments = line.split('#', 1)[0].strip()
            if not strip_comments:
                continue

            pieces = strip_comments.split(';')
            assert len(pieces) == 3

            variation_sequence, description, differences = pieces[0], pieces[1].strip(), pieces[2]

            # Don't use variations that only apply in particular shaping environments.
            if differences:
                continue

            # Look for entries where the description field is a codepoint name.
            if description in self.name_to_char_int:
                char_int = self.name_to_char_int[description]

                assert not char_int in self.combining_classes, "Unexpected: standardized variant with a combining class"
                assert not char_int in self.compat_decomp, "Unexpected: standardized variant and compatibility decomposition"
                assert len(self.canon_decomp[char_int]) == 1, "Unexpected: standardized variant and non-singleton canonical decomposition"
                # If we ever need to handle Hangul here, we'll need to handle it separately.
                assert not (S_BASE <= char_int < S_BASE + S_COUNT)

                standardized_variant_parts = [int(c, 16) for c in variation_sequence.split()]
                for c in standardized_variant_parts:
                    #assert not never_composes(c) TODO: Re-enable this once #67 lands.
                    assert not c in self.canon_decomp, "Unexpected: standardized variant is unnormalized (canon)"
                    assert not c in self.compat_decomp, "Unexpected: standardized variant is unnormalized (compat)"
                self.svar_decomp[char_int] = standardized_variant_parts
                self.svar_fully_decomp[char_int] = standardized_variant_parts

    def _load_norm_props(self):
        props = collections.defaultdict(list)

        for line in self._fetch("DerivedNormalizationProps.txt").splitlines():
            (prop_data, _, _) = line.partition("#")
            prop_pieces = prop_data.split(";")

            if len(prop_pieces) < 2:
                continue

            assert len(prop_pieces) <= 3
            (low, _, high) = prop_pieces[0].strip().partition("..")

            prop = prop_pieces[1].strip()

            data = None
            if len(prop_pieces) == 3:
                data = prop_pieces[2].strip()

            props[prop].append((low, high, data))

        return props

    def _load_norm_tests(self):
        tests = []
        for line in self._fetch("NormalizationTest.txt").splitlines():
            (test_data, _, _) = line.partition("#")
            test_pieces = test_data.split(";")

            if len(test_pieces) < 5:
                continue

            source, nfc, nfd, nfkc, nfkd = [[c.strip() for c in p.split()] for p in test_pieces[:5]]
            tests.append(NormalizationTest(source, nfc, nfd, nfkc, nfkd))

        return tests

    def _compute_canonical_comp(self):
        canon_comp = {}
        comp_exclusions = [
            (int(low, 16), int(high or low, 16))
            for low, high, _ in self.norm_props["Full_Composition_Exclusion"]
        ]
        for char_int, decomp in self.canon_decomp.items():
            if any(lo <= char_int <= hi for lo, hi in comp_exclusions):
                continue

            assert len(decomp) == 2
            assert (decomp[0], decomp[1]) not in canon_comp
            canon_comp[(decomp[0], decomp[1])] = char_int

        return canon_comp

    def _compute_fully_decomposed(self):
        """
        Even though the decomposition algorithm is recursive, it is possible
        to precompute the recursion at table generation time with modest
        increase to the table size.  Then, for these precomputed tables, we
        note that 1) compatible decomposition is a subset of canonical
        decomposition and 2) they mostly agree on their intersection.
        Therefore, we don't store entries in the compatible table for
        characters that decompose the same way under canonical decomposition.

            Decomposition table stats:
            Canonical decomp: 2060 chars => 3085 decomposed chars
            Compatible decomp: 3662 chars => 5440 decomposed chars
            Canonical fully decomp: 2060 chars => 3404 decomposed chars
            Compatible fully decomp: 3678 chars => 5599 decomposed chars

        The upshot is that decomposition code is very simple and easy to inline
        at mild code size cost.
        """
        def _decompose(char_int, compatible):
            # 7-bit ASCII never decomposes
            if char_int <= 0x7f:
                yield char_int
                return

            # Assert that we're handling Hangul separately.
            assert not (S_BASE <= char_int < S_BASE + S_COUNT)

            decomp = self.canon_decomp.get(char_int)
            if decomp is not None:
                for decomposed_ch in decomp:
                    for fully_decomposed_ch in _decompose(decomposed_ch, compatible):
                        yield fully_decomposed_ch
                return

            if compatible and char_int in self.compat_decomp:
                for decomposed_ch in self.compat_decomp[char_int]:
                    for fully_decomposed_ch in _decompose(decomposed_ch, compatible):
                        yield fully_decomposed_ch
                return

            yield char_int
            return

        end_codepoint = max(
            max(self.canon_decomp.keys()),
            max(self.compat_decomp.keys()),
        )

        canon_fully_decomp = {}
        compat_fully_decomp = {}

        for char_int in range(0, end_codepoint + 1):
            # Always skip Hangul, since it's more efficient to represent its
            # decomposition programmatically.
            if S_BASE <= char_int < S_BASE + S_COUNT:
                continue

            canon = list(_decompose(char_int, False))
            if not (len(canon) == 1 and canon[0] == char_int):
                canon_fully_decomp[char_int] = canon

            compat = list(_decompose(char_int, True))
            if not (len(compat) == 1 and compat[0] == char_int):
                compat_fully_decomp[char_int] = compat

        # Since canon_fully_decomp is a subset of compat_fully_decomp, we don't
        # need to store their overlap when they agree.  When they don't agree,
        # store the decomposition in the compatibility table since we'll check
        # that first when normalizing to NFKD.
        assert set(canon_fully_decomp) <= set(compat_fully_decomp)

        for ch in set(canon_fully_decomp) & set(compat_fully_decomp):
            if canon_fully_decomp[ch] == compat_fully_decomp[ch]:
                del compat_fully_decomp[ch]

        return canon_fully_decomp, compat_fully_decomp

    def _compute_stream_safe_tables(self):
        """
        To make a text stream-safe with the Stream-Safe Text Process (UAX15-D4),
        we need to be able to know the number of contiguous non-starters *after*
        applying compatibility decomposition to each character.

        We can do this incrementally by computing the number of leading and
        trailing non-starters for each character's compatibility decomposition
        with the following rules:

        1) If a character is not affected by compatibility decomposition, look
           up its canonical combining class to find out if it's a non-starter.
        2) All Hangul characters are starters, even under decomposition.
        3) Otherwise, very few decomposing characters have a nonzero count
           of leading or trailing non-starters, so store these characters
           with their associated counts in a separate table.
        """
        leading_nonstarters = {}
        trailing_nonstarters = {}

        for c in set(self.canon_fully_decomp) | set(self.compat_fully_decomp):
            decomposed = self.compat_fully_decomp.get(c) or self.canon_fully_decomp[c]

            num_leading = 0
            for d in decomposed:
                if d not in self.combining_classes:
                    break
                num_leading += 1

            num_trailing = 0
            for d in reversed(decomposed):
                if d not in self.combining_classes:
                    break
                num_trailing += 1

            if num_leading > 0:
                leading_nonstarters[c] = num_leading
            if num_trailing > 0:
                trailing_nonstarters[c] = num_trailing

        return leading_nonstarters, trailing_nonstarters

hexify = lambda c: '{:04X}'.format(c)

def gen_mph_data(name, d, kv_type, kv_callback):
    (salt, keys) = minimal_perfect_hash(d)
    out.write("pub(crate) const %s_SALT: &[u16] = &[\n" % name.upper())
    for s in salt:
        out.write("    0x{:x},\n".format(s))
    out.write("];\n")
    out.write("pub(crate) const {}_KV: &[{}] = &[\n".format(name.upper(), kv_type))
    for k in keys:
        out.write("    {},\n".format(kv_callback(k)))
    out.write("];\n\n")

def gen_combining_class(combining_classes, out):
    gen_mph_data('canonical_combining_class', combining_classes, 'u32',
        lambda k: "0x{:X}".format(int(combining_classes[k]) | (k << 8)))

def gen_composition_table(canon_comp, out):
    table = {}
    for (c1, c2), c3 in canon_comp.items():
        if c1 < 0x10000 and c2 < 0x10000:
            table[(c1 << 16) | c2] = c3
    (salt, keys) = minimal_perfect_hash(table)
    gen_mph_data('COMPOSITION_TABLE', table, '(u32, char)',
        lambda k: "(0x%s, '\\u{%s}')" % (hexify(k), hexify(table[k])))

    out.write("pub(crate) fn composition_table_astral(c1: char, c2: char) -> Option<char> {\n")
    out.write("    match (c1, c2) {\n")
    for (c1, c2), c3 in sorted(canon_comp.items()):
        if c1 >= 0x10000 and c2 >= 0x10000:
            out.write("        ('\\u{%s}', '\\u{%s}') => Some('\\u{%s}'),\n" % (hexify(c1), hexify(c2), hexify(c3)))

    out.write("        _ => None,\n")
    out.write("    }\n")
    out.write("}\n")

def gen_decomposition_tables(canon_decomp, compat_decomp, svar_decomp, out):
    tables = [(canon_decomp, 'canonical'), (compat_decomp, 'compatibility'), (svar_decomp, 'svar')]
    for table, name in tables:
        gen_mph_data(name + '_decomposed', table, "(u32, &'static [char])",
            lambda k: "(0x{:x}, &[{}])".format(k,
                ", ".join("'\\u{%s}'" % hexify(c) for c in table[k])))

def gen_qc_match(prop_table, out):
    out.write("    match c {\n")

    for low, high, data in prop_table:
        assert data in ('N', 'M')
        result = "No" if data == 'N' else "Maybe"
        if high:
            out.write(r"        '\u{%s}'...'\u{%s}' => %s," % (low, high, result))
        else:
            out.write(r"        '\u{%s}' => %s," % (low, result))
        out.write("\n")

    out.write("        _ => Yes,\n")
    out.write("    }\n")

def gen_nfc_qc(prop_tables, out):
    out.write("#[inline]\n")
    out.write("#[allow(ellipsis_inclusive_range_patterns)]\n")
    out.write("pub fn qc_nfc(c: char) -> IsNormalized {\n")
    gen_qc_match(prop_tables['NFC_QC'], out)
    out.write("}\n")

def gen_nfkc_qc(prop_tables, out):
    out.write("#[inline]\n")
    out.write("#[allow(ellipsis_inclusive_range_patterns)]\n")
    out.write("pub fn qc_nfkc(c: char) -> IsNormalized {\n")
    gen_qc_match(prop_tables['NFKC_QC'], out)
    out.write("}\n")

def gen_nfd_qc(prop_tables, out):
    out.write("#[inline]\n")
    out.write("#[allow(ellipsis_inclusive_range_patterns)]\n")
    out.write("pub fn qc_nfd(c: char) -> IsNormalized {\n")
    gen_qc_match(prop_tables['NFD_QC'], out)
    out.write("}\n")

def gen_nfkd_qc(prop_tables, out):
    out.write("#[inline]\n")
    out.write("#[allow(ellipsis_inclusive_range_patterns)]\n")
    out.write("pub fn qc_nfkd(c: char) -> IsNormalized {\n")
    gen_qc_match(prop_tables['NFKD_QC'], out)
    out.write("}\n")

def gen_combining_mark(general_category_mark, out):
    gen_mph_data('combining_mark', general_category_mark, 'u32',
        lambda k: '0x{:04x}'.format(k))

def gen_stream_safe(leading, trailing, out):
    # This could be done as a hash but the table is very small.
    out.write("#[inline]\n")
    out.write("pub fn stream_safe_leading_nonstarters(c: char) -> usize {\n")
    out.write("    match c {\n")

    for char, num_leading in sorted(leading.items()):
        out.write("        '\\u{%s}' => %d,\n" % (hexify(char), num_leading))

    out.write("        _ => 0,\n")
    out.write("    }\n")
    out.write("}\n")
    out.write("\n")

    gen_mph_data('trailing_nonstarters', trailing, 'u32',
        lambda k: "0x{:X}".format(int(trailing[k]) | (k << 8)))

def gen_tests(tests, out):
    out.write("""#[derive(Debug)]
pub struct NormalizationTest {
    pub source: &'static str,
    pub nfc: &'static str,
    pub nfd: &'static str,
    pub nfkc: &'static str,
    pub nfkd: &'static str,
}

""")

    out.write("pub const NORMALIZATION_TESTS: &[NormalizationTest] = &[\n")
    str_literal = lambda s: '"%s"' % "".join("\\u{%s}" % c for c in s)

    for test in tests:
        out.write("    NormalizationTest {\n")
        out.write("        source: %s,\n" % str_literal(test.source))
        out.write("        nfc: %s,\n" % str_literal(test.nfc))
        out.write("        nfd: %s,\n" % str_literal(test.nfd))
        out.write("        nfkc: %s,\n" % str_literal(test.nfkc))
        out.write("        nfkd: %s,\n" % str_literal(test.nfkd))
        out.write("    },\n")

    out.write("];\n")

# Guaranteed to be less than n.
def my_hash(x, salt, n):
    # This is hash based on the theory that multiplication is efficient
    mask_32 = 0xffffffff
    y = ((x + salt) * 2654435769) & mask_32
    y ^= (x * 0x31415926) & mask_32
    return (y * n) >> 32

# Compute minimal perfect hash function, d can be either a dict or list of keys.
def minimal_perfect_hash(d):
    n = len(d)
    buckets = dict((h, []) for h in range(n))
    for key in d:
        h = my_hash(key, 0, n)
        buckets[h].append(key)
    bsorted = [(len(buckets[h]), h) for h in range(n)]
    bsorted.sort(reverse = True)
    claimed = [False] * n
    salts = [0] * n
    keys = [0] * n
    for (bucket_size, h) in bsorted:
        # Note: the traditional perfect hashing approach would also special-case
        # bucket_size == 1 here and assign any empty slot, rather than iterating
        # until rehash finds an empty slot. But we're not doing that so we can
        # avoid the branch.
        if bucket_size == 0:
            break
        else:
            for salt in range(1, 32768):
                rehashes = [my_hash(key, salt, n) for key in buckets[h]]
                # Make sure there are no rehash collisions within this bucket.
                if all(not claimed[hash] for hash in rehashes):
                    if len(set(rehashes)) < bucket_size:
                        continue
                    salts[h] = salt
                    for key in buckets[h]:
                        rehash = my_hash(key, salt, n)
                        claimed[rehash] = True
                        keys[rehash] = key
                    break
            if salts[h] == 0:
                print("minimal perfect hashing failed")
                # Note: if this happens (because of unfortunate data), then there are
                # a few things that could be done. First, the hash function could be
                # tweaked. Second, the bucket order could be scrambled (especially the
                # singletons). Right now, the buckets are sorted, which has the advantage
                # of being deterministic.
                #
                # As a more extreme approach, the singleton bucket optimization could be
                # applied (give the direct address for singleton buckets, rather than
                # relying on a rehash). That is definitely the more standard approach in
                # the minimal perfect hashing literature, but in testing the branch was a
                # significant slowdown.
                exit(1)
    return (salts, keys)

if __name__ == '__main__':
    data = UnicodeData()
    with open("tables.rs", "w", newline = "\n") as out:
        out.write(PREAMBLE)
        out.write("use crate::quick_check::IsNormalized;\n")
        out.write("use crate::quick_check::IsNormalized::*;\n")
        out.write("\n")

        version = "(%s, %s, %s)" % tuple(UNICODE_VERSION.split("."))
        out.write("#[allow(unused)]\n")
        out.write("pub const UNICODE_VERSION: (u8, u8, u8) = %s;\n\n" % version)

        gen_combining_class(data.combining_classes, out)
        out.write("\n")

        gen_composition_table(data.canon_comp, out)
        out.write("\n")

        gen_decomposition_tables(data.canon_fully_decomp, data.compat_fully_decomp, data.svar_fully_decomp, out)

        gen_combining_mark(data.general_category_mark, out)
        out.write("\n")

        gen_nfc_qc(data.norm_props, out)
        out.write("\n")

        gen_nfkc_qc(data.norm_props, out)
        out.write("\n")

        gen_nfd_qc(data.norm_props, out)
        out.write("\n")

        gen_nfkd_qc(data.norm_props, out)
        out.write("\n")

        gen_stream_safe(data.ss_leading, data.ss_trailing, out)
        out.write("\n")

    with open("normalization_tests.rs", "w", newline = "\n") as out:
        out.write(PREAMBLE)
        gen_tests(data.norm_tests, out)
