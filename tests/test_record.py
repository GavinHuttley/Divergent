from itertools import product
from pathlib import Path

import numpy
import pytest

from cogent3 import get_moltype, make_seq
from numpy import nextafter, ravel_multi_index, unravel_index
from numpy.testing import assert_allclose

from divergent.record import (
    SeqRecord,
    coord_conversion_coeffs,
    coord_to_index,
    index_to_coord,
    kmer_indices,
    seq2array,
    seq_to_kmer_counts,
    sparse_vector,
    unique_kmers,
)


DATADIR = Path(__file__).parent / "data"


seq5 = make_seq("ACGCG", name="null", moltype="dna")
seq0 = make_seq("", name="null", moltype="dna")
seq_nameless = make_seq("ACGTGTT", moltype="dna")
seq4eq = make_seq("ACGT", name="null", moltype="dna")
seq4one = make_seq("AAAA", name="null", moltype="dna")


@pytest.mark.parametrize("seq,entropy", ((seq4eq, 2.0), (seq4one, 0.0)))
def test_seqrecord_entropy(seq, entropy):
    sr = SeqRecord(seq=seq, moltype="dna", k=1)
    assert sr.entropy == entropy


@pytest.mark.parametrize("seq,k", ((seq0, 1), (seq5, -1), (seq5, 100)))
def test_seqrecord_invalid_input(seq, k):
    with pytest.raises(ValueError):
        SeqRecord(seq=seq, moltype="dna", k=k)


@pytest.mark.parametrize("seq,k", ((seq_nameless, 1), (seq5, 0.1)))
def test_seqrecord_invalid_types(seq, k):
    with pytest.raises(TypeError):
        SeqRecord(seq=seq, moltype="dna", k=k)


def test_seqrecord_compare():
    sr1 = SeqRecord(seq=seq5, moltype="dna", k=2)
    sr1.delta_jsd = 1.0
    sr2 = SeqRecord(seq=seq5, moltype="dna", k=2)
    sr2.delta_jsd = 2.0
    sr3 = SeqRecord(seq=seq5, moltype="dna", k=2)
    sr3.delta_jsd = 34.0

    rec = sorted((sr3, sr1, sr2))
    assert rec[0].delta_jsd == 1 and rec[-1].delta_jsd == 34


@pytest.mark.parametrize("k", (1, 2, 3))
def test_seq_to_kmer_counts_kfreqs(k):
    from collections import Counter

    from numpy import unravel_index

    s2k = seq_to_kmer_counts(k=k, moltype="dna")
    kcounts = s2k(seq5)
    assert kcounts.size == 4 ** k
    assert kcounts.sum() == len(seq5) - k + 1
    # check we can round trip the counts
    int2str = lambda x: "".join(
        seq5.moltype.alphabet.from_indices(unravel_index(x, shape=(4,) * k))
    )
    expected = Counter(seq5.iter_kmers(k))
    got = {int2str(i): c for i, c in enumerate(kcounts) if c}
    assert got == expected


def test_sparse_vector_create():
    from numpy import array

    data = {2: 3, 3: 9}
    # to constructor
    v1 = sparse_vector(data=data, size=5, dtype=int)
    expect = array([0, 0, 3, 9, 0])
    assert_allclose(v1.array, expect)

    # or via set item individually
    v2 = sparse_vector(size=5)
    for index, count in data.items():
        v2[index] = count

    assert v1.data == v2.data


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_add_vector(cast):
    # adds two vectors
    data = {2: 3, 3: 9}
    v1 = sparse_vector(data=data, size=5, dtype=cast)

    # add to zero vector
    v0 = sparse_vector(size=5, dtype=cast)
    v_ = v1 + v0
    assert v_.data == v1.data
    assert v_.data is not v1.data

    # add to self
    v3 = v1 + v1
    assert v3.data == {k: v * 2 for k, v in data.items()}

    # add in-place
    v1 += v1
    assert v1.data == {k: v * 2 for k, v in data.items()}


@pytest.mark.parametrize("zero", (0, 0.0, nextafter(0.0, 1.0) / 2))
def test_sparse_vector_add_zero(zero):
    # does not include
    expect = {2: 3.0, 3: 9.0}
    data = {1: zero, **expect}
    v1 = sparse_vector(data=data, size=5, dtype=float)
    assert v1.data == expect


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_add_scalar(cast):
    # adds two vectors
    data = {2: 3, 3: 9}
    v1 = sparse_vector(data=data, size=5, dtype=cast)

    # add to zero vector
    v0 = sparse_vector(size=5, dtype=cast)
    v_ = v1 + 0
    assert v_.data == v1.data
    assert v_.data is not v1.data

    # add in place
    v1 += 5
    assert v1.data == {k: v + 5 for k, v in data.items()}


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_sub_vector(cast):
    # sub two vectors
    data = {2: 3, 3: 9}
    v1 = sparse_vector(data=data, size=5, dtype=cast)
    # sub self
    v3 = v1 - v1
    assert v3.data == {}

    data2 = {2: 3, 3: 10}
    v2 = sparse_vector(data=data2, size=5, dtype=cast)
    v3 = v2 - v1
    assert v3.data == {3: cast(1)}

    # sub in-place
    v1 -= v2
    assert v1.data == {k: v - data2[k] for k, v in data.items()}

    # negative allowed
    data = {2: 3, 3: 9}
    v1 = sparse_vector(data=data, size=5, dtype=cast)
    data2 = {2: 6, 3: 10}
    v2 = sparse_vector(data=data2, size=5, dtype=cast)
    v3 = v1 - v2
    assert v3[2] == -3


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_sub_scalar(cast):
    # subtracts two vectors
    data = {2: 3, 3: 9}
    v1 = sparse_vector(data=data, size=5, dtype=cast)

    # subtract zero
    v_ = v1 - 0
    assert v_.data == v1.data
    assert v_.data is not v1.data

    # subtract in place
    v1 -= 2
    assert v1.data == {k: v - 2 for k, v in data.items()}


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_sub_elementwise(cast):
    data = {2: 3, 3: 9}
    v2 = sparse_vector(data=data, size=5, dtype=cast)
    v2[1] -= 99
    assert v2[1] == -99
    assert type(v2[1]) == cast


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_elementwise(cast):
    data = {2: 3, 3: 9}
    v2 = sparse_vector(data=data, size=5, dtype=cast)
    v2[1] += 99
    assert v2[1] == 99
    assert type(v2[1]) == cast
    del v2[1]
    assert v2[1] == 0
    assert type(v2[1]) == cast


def test_sparse_vector_sum():
    sv = sparse_vector(size=20, dtype=int)
    assert sv.sum() == 0


def test_sparse_vector_iter_nonzero():
    data = {3: 9, 2: 3}
    sv = sparse_vector(data=data, size=20, dtype=int)
    got = list(sv.iter_nonzero())
    assert got == [3, 9]


def test_sv_iter():
    from numpy import array, ndarray

    sv = sparse_vector(data={2: 1, 1: 1, 3: 1, 0: 1}, size=4, dtype=int)
    sv /= sv.sum()
    got = list(sv.iter_nonzero())
    assert_allclose(got, 0.25)
    arr = array(got)


def test_sv_pickling():
    import pickle

    o = sparse_vector(data={2: 1, 1: 1, 3: 1, 0: 1}, size=4, dtype=int)
    p = pickle.dumps(o)
    u = pickle.loads(p)
    assert str(u) == str(o)


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_div_vector(cast):
    # adds two vectors
    data1 = {2: 6, 3: 18}
    v1 = sparse_vector(data=data1, size=5, dtype=cast)

    # factored by 3
    data2 = {2: 3, 3: 3}
    v2 = sparse_vector(data=data2, size=5, dtype=cast)
    v3 = v1 / v2
    assert v3.data == {k: v / 3 for k, v in data1.items()}

    # different factors
    data2 = {2: 3, 3: 6}
    v2 = sparse_vector(data=data2, size=5, dtype=cast)
    v3 = v1 / v2
    expect = {2: 2, 3: 3}
    assert v3.data == expect

    # div in-place
    v1 /= v2
    assert v1.data == expect


@pytest.mark.parametrize("cast", (float, int))
def test_sparse_vector_div_scalar(cast):
    # adds two vectors
    data1 = {2: 6, 3: 18}
    v1 = sparse_vector(data=data1, size=5, dtype=cast)

    # factored by 3
    v2 = v1 / 3
    expect = {k: v / 3 for k, v in data1.items()}
    assert v2.data == expect
    assert v2.data is not v1.data

    # div in-place
    v1 /= 3
    assert v1.data == expect


@pytest.mark.parametrize("num_states,ndim", ((2, 1), (4, 2), (4, 4)))
def test_interconversion_of_coords_indices(num_states, ndim):
    # make sure match numpy functions
    coeffs = numpy.array(coord_conversion_coeffs(num_states, ndim))
    for coord in product(*(list(range(num_states)),) * ndim):
        coord = numpy.array(coord, dtype=numpy.int64)
        nidx = ravel_multi_index(coord, dims=(num_states,) * ndim)
        idx = coord_to_index(coord, coeffs)
        assert idx == nidx
        ncoord = unravel_index(nidx, shape=(num_states,) * ndim)
        got = index_to_coord(idx, coeffs)
        assert (got == ncoord).all()
        assert (got == coord).all()


def test_coord2index_fail():
    coord = numpy.array((0, 1), dtype=numpy.int64)
    coeffs = numpy.array(coord_conversion_coeffs(2, 4))
    # dimension of coords inconsistent with coeffs
    with pytest.raises(ValueError):
        coord_to_index(coord, coeffs)


def test_unique_kmer_pickling():
    import pickle

    kwargs = dict(size=4 ** 2, name="abc", source="abc", data=numpy.array([0, 2, 3]))
    o = unique_kmers(**kwargs)
    p = pickle.dumps(o)
    u = pickle.loads(p)
    assert str(o) == str(u)


def test_unique_kmer_len():
    o = unique_kmers(size=4 ** 2, name="abc", source="abc", data=numpy.array([0, 2, 3]))
    assert len(o) == 3

    o = unique_kmers(size=4 ** 2, name="abc", source="abc")
    assert len(o) == 0


def test_seq2arry():
    dna = get_moltype("dna")
    s = b"ACGTT"
    r = numpy.zeros(len(s), dtype=int)
    bases = "".join(dna).encode("utf8")
    expect = dna.alphabet.to_indices(s.decode("utf8"))
    g = seq2array(s, r, bases)
    assert g.tolist() == expect
    g = seq2array(b"ACGNT", r, bases)
    assert g[-2] == -1  # non-canonical characters are -1


def test_seq2kmers():
    from divergent.record import coord_conversion_coeffs

    k = 2
    dtype = numpy.int64
    coeffs = numpy.array(coord_conversion_coeffs(4, k), dtype=dtype)

    dna = get_moltype("dna")

    s = b"ACGGCGGTGCA"
    indices = numpy.zeros(len(s), dtype=dtype)
    bases = "".join(dna).encode("utf8")
    indices = seq2array(s, indices, bases)
    result = numpy.zeros(len(s) - k + 1, dtype=numpy.int64)
    got = kmer_indices(indices, coeffs, result, k)

    expect = [
        numpy.ravel_multi_index(indices[i : i + k], dims=(4,) * k)
        for i in range(len(s) - k + 1)
    ]
    assert (got == expect).all()
