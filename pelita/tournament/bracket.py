import enum
from itertools import zip_longest
from numpy import isin, row_stack
from pyparsing import col


tree0 = [333, 1, 31]
tree = [[21111111112, 4, 31], 100000, [11, 2, 1111]]

tree = [tree, 100000, "NNN"]

tree1 = \
    [
    [1, 2, 3],
    4,
    [5, 6, 7],
    ]

tree1 = \
    [
        [
            [1, 2, 3], 4, [5, 6, 7]
        ],
                8,
        [
            [9, 10, 11], 12, [13, 14, 15]
        ]
    ]


tree2 = \
    [
        [
            [1, 2, 3], 4, [5, 6, 7]
        ],
                8,
        [
            10, 12, [13, 14, 15]
        ]
    ]

def merge_widths(l, r) -> list:
    return [max(ll, rr) for ll, rr in zip_longest(l, r, fillvalue=0)]

def col_widths(tree):
    if not isinstance(tree, list):
        return [len(str(tree))]

    head, elem, btm = tree

    prev = col_widths(head)
    next = col_widths(btm)

    prior_widths = merge_widths(prev, next)

    return [len(str(elem))] + prior_widths


def gen_tree(tree, *, col_widths=None, depth=0):
    # Note: The algorithm is not 100% correct in all cases in that it
    # generates a proper bracket.

    # max text length of the elements in a col
    col_elem_len = col_widths[depth] if col_widths else 0

    if not isinstance(tree, list):
        elem = f" {tree} ".ljust(col_elem_len + 2, '─')
        #elem = f" {tree} ".ljust(col_elem_len + 2)
        indent = len(elem)
        return [elem], indent, 0

    head, elem, btm = tree
    #elem = str(elem)

    prev, indent_prev, prev_idx = gen_tree(head, depth=depth+1, col_widths=col_widths)
    next, indent_next, next_idx = gen_tree(btm, depth=depth+1, col_widths=col_widths)

    indent = max(indent_prev, indent_next)

    if depth == 0:
        middle = f"├──┨ {elem: <{col_elem_len}} ┃"
    else:
        middle = f"├─ {elem + ' ':─<{col_elem_len + 1}}"
        # middle = f"├─ {elem : <{col_elem_len}} "

    line_length = indent + len(middle)
    connector_col = indent + 1

    middle_idx = len(prev)

    def gen_block():
        # Add connectors to prev
        for idx, line in enumerate(prev):
            if idx < prev_idx:
                char = ""
            elif idx == prev_idx:
                line = line.rjust(indent)
                char = "┐"
            else:
                line = line.ljust(indent)
                char = "│"
            if depth == 0 and idx == len(prev) - 1:
                char += "  ┏━" + ("━" * len(elem)) + "━┓"
            yield f"{line}{char}"

        yield middle.rjust(line_length)

        # Add connectors to next
        for idx, line in enumerate(next):
            if idx > next_idx:
                char = ""
            elif idx == next_idx:
                line = line.rjust(indent)
                char = "┘"
            else:
                line = line.ljust(indent)
                char = "│"
            if depth == 0 and idx == 0:
                char += f"  ┗━" + "━" * len(elem) + "━┛"
            yield f"{line}{char}" # .ljust(col_elem_len + 2) #.ljust(indent).rjust(line_length)

    block = list(gen_block())

    return block, line_length, middle_idx

def print_tree(tree):
    return "\n".join(gen_tree(tree, col_widths=col_widths(tree))[0])

#print(col_widths(tree0))
#print(col_widths(tree0))
#print(col_widths(tree2))

#print("\n".join(print_tree(tree0)))

#print(print_tree(tree2))


def gen_order(m):
    # we assume that n == 2**m
    # first we generate the order for 2**(m-1)
    # then for each number i, we add n-i-1 to its right.
    # [0                     ]
    # [0,          1         ]
    # [0,    3,    1,    2   ]
    # [0, 7, 3, 4, 1, 6, 2, 5]

    # We seed stronger teams with a lower number.
    # If we assume that all matches have the likely outcome with the team
    # winning that has the lower number, this ensures consistency through
    # all rounds. (Ie. the strongest team will play the weakest enemy each round.)


    if m == 0:
        return [0]

    n = 2**m

    lower_order = gen_order(m - 1)
    result = []
    for i in lower_order:
        result.append(i)
        result.append(n - i - 1)

    return result

team5 = [[[1, "long team name", 3], "???", [4, 5, 6]], "???", 0]

#print(print_tree(team5))

#print(print_tree(tree2))

import pytest
from textwrap import dedent


@pytest.mark.parametrize('teams, test_col_widths', [
    ([[[1, "???", 4], "???", [2, "???", 3]], "???", 5], [3, 3, 3, 1]),
])
def test_col_widths(teams, test_col_widths):
    assert col_widths(teams) == test_col_widths

@pytest.mark.parametrize('teams, check_output', [
    ([[[1, "???", 4], "???", [2, "???", 3]], "???", 5], """
        1 ┐
          ├─ ??? ┐
        4 ┘      │
                 ├─ ??? ┐
        2 ┐      │      │
          ├─ ??? ┘      │
        3 ┘             │  ┏━━━━━┓
                        ├──┨ ??? ┃
                    5 ──┘  ┗━━━━━┛
        """),
])
def test_bracket(teams, check_output):
    printed = print_tree(teams)

    print(dedent(printed).strip())
    print(dedent(check_output).strip())

    assert dedent(printed).strip() == dedent(check_output).strip()

@pytest.mark.parametrize('num, check_output', [
    [0, [0]],
    [1, [0, 1]],
    [2, [0, 3, 1, 2]],
    [4, [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10]],
])
def test_gen_order(num, check_output):
    assert gen_order(num) == check_output
