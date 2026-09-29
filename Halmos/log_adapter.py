"""Expose committed EVM logs to Solidity checks using Halmos's execution trace.

This adapter supports recordLogs/getRecordedLogs in the test's current call frame.
It deliberately excludes reverted call subtrees, and getRecordedLogs drains the
recording. It is not a complete implementation of Foundry's recorder semantics.
"""
from halmos.bytevec import ByteVec
from halmos.cheatcodes import hevm_cheat_code
from halmos.sevm import CallContext, EventLog
from halmos.utils import int_of, uint256

RECORD = 0x41AF2F52 # fn selector for recordLogs()
GET = 0x191553A4 # fn selector for getRecordedLogs()


def marker(item):
    if isinstance(item, CallContext) and item.message.target == hevm_cheat_code.address:
        return int_of(item.message.data[:4].unwrap(), "symbolic recorder selector")
    return None


def committed_logs(trace):
    for item in trace:
        if isinstance(item, EventLog):
            yield item
        elif isinstance(item, CallContext) and item.output.error is None:
            yield from committed_logs(item.trace)


def encode_logs(logs):
    result = ByteVec()
    result.set_word(0, 32)
    result.set_word(32, len(logs))
    offset = 32 * len(logs)
    for i, log in enumerate(logs):
        result.set_word(64 + 32 * i, offset)
        entry = ByteVec()
        entry.set_word(0, 96)
        entry.set_word(32, 128 + 32 * len(log.topics))
        entry.set_word(64, uint256(log.address))
        entry.set_word(96, len(log.topics))
        for j, topic in enumerate(log.topics):
            entry.set_word(128 + 32 * j, topic)
        data = ByteVec(log.data) if log.data is not None else ByteVec()
        entry.set_word(len(entry), len(data))
        entry.append(data)
        entry.append(bytes((-len(data)) % 32))
        result[64 + offset:64 + offset + len(entry)] = entry
        offset += len(entry)
    return result


def install():
    original = hevm_cheat_code.handle

    def handle(sevm, ex, arg, stack):
        selector = int_of(arg[:4].unwrap(), "symbolic hevm cheatcode")
        if selector == RECORD:
            return ByteVec()
        if selector == GET:
            trace = ex.context.trace
            start = None
            recorded = False
            for i, item in enumerate(trace):
                kind = marker(item)
                if kind == RECORD:
                    recorded = True
                    start = i + 1
                elif kind == GET and recorded:
                    start = i + 1
            if start is None:
                raise RuntimeError("getRecordedLogs requires recordLogs in the same call frame")
            return encode_logs(list(committed_logs(trace[start:])))
        return original(sevm, ex, arg, stack)

    hevm_cheat_code.handle = staticmethod(handle)
