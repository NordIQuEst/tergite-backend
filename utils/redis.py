# This code is part of Tergite
#
# (C) Copyright David Wahlstedt 2021
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import re

# How much to indent each level
ind_step = 2

# Dump the Redis database, and by default exclude entries generated by
# the rq package
#
# optional argument regex: dump all keys matching the regular expression regex
#
# Todo: put the contents in a nested dict instead, and do the printing separately.
def dump_redis(red, msg="", regex="(?!rq:)"):
    print(f"---- Redis dump: {msg} ----")

    re_prog = compile_re(regex)
    if not re_prog:
        return

    keys = red.scan_iter("*")
    print("{")

    for key in list(filter(lambda k: re_prog.match(k), sorted(keys))):
        ty = red.type(key)
        qkey = quote(f"{key}")

        if ty == "hash":
            print(indent(1, qkey + ": {"))
            hgetallres = red.hgetall(key)
            for rk in sorted(hgetallres):
                hkey = f"{rk}"
                hval = f"{hgetallres[rk]}"
                print(indent(2, (quote(hkey) + ": " + quote(hval) + ",")))
            print(indent(1, "},"))
        elif ty == "list":
            qval = f"{red.lrange(key,0,-1)}"
            print(indent(1, qkey + ": " + qval + ","))
        elif ty == "string":
            qval = f"{red.get(key)}"
            print(indent(1, qkey + ": " + qval + ","))
        elif ty == "set":
            qval = f"{red.smembers(key)}"
            print(indent(1, qkey + ": " + qval + ","))
        elif ty == "zset":
            qval = f"{red.zrange(key,0,-1, withscores=True)}"
            print(indent(1, qkey + ": " + qval + ","))
        elif ty == "stream":
            qval = f"{red.xrange(key,'-','+')}"
            print(indent(1, qkey + ": " + qval + ","))
        else:
            print(f"unknown type: {key=}, {ty=}")
    print("}")
    print(f"---- END Redis dump: {msg} ----")


# Deletes all keys matching the given regular expression
def del_keys(red, regex):
    re_prog = compile_re(regex)
    if not re_prog:
        return

    keys = red.scan_iter("*")
    for key in list(filter(lambda k: re_prog.match(k), keys)):
        red.delete(key)


# Delete all keys *not* related to the Redis queue "rq" package
def del_non_rq(red):
    del_keys(red, "(?!rq:)")


# Misc helpers


def compile_re(regex):
    try:
        re_prog = re.compile(regex)
    except Exception as error:
        print(f"regex compilation failed: {regex}, {error}, aborting Redis dump.")
        return None
    return re_prog


def quote(s):
    return '"' + s + '"'


def indent(n, s):
    return ind_step * n * " " + s
