# Dump the redis database, and by default exclude entries generated by the rq package
# Todo: put the contents in a netsed dict instead, and do the printing separately.
def dump_redis(red, msg="", exclude_prefix="rq:"):
    print(f"----------------------- redis dump: {msg} ------------------------")
    keys = red.scan_iter("*")
    ind = "  "
    print("{")

    for key in list(filter(lambda k: not k.startswith(exclude_prefix), sorted(keys))):
        ty = red.type(key)
        qkey = quote(f"{key}")

        if ty == "hash":
            print(qkey + ': {')
            hgetallres = red.hgetall(key)
            for rk in sorted(hgetallres):
                hkey = f"{rk}"
                hval = f"{hgetallres[rk]}"
                print(ind + quote(hkey) + ": " + quote(hval) + ",")
            print("},")
        elif ty == "list":
            qval = f"{red.lrange(key,0,-1)}"
            print(qkey + ": " + qval + ",")
        elif ty == "string":
            qval = f"{red.get(key)}"
            print(qkey + ": " + qval + ",")
        elif ty == "set":
            qval = f"{red.smembers(key)}"
            print(qkey + ": " + qval + ",")
        elif ty == "zset":
            qval = f"{red.zrange(key,0,-1, withscores=True)}"
            print(qkey+": " + qval + ",")
        elif ty == "stream":
            qval = f"{red.xrange(key,'-','+')}"
            print(qkey+": " + qval + ",")
        else:
            print(f"unknown type: {key=}, {ty=}")
    print("}")
    print(f"----------------------- END redis dump: {msg} ------------------------")

def quote(s):
    return "\"" + s + "\""
