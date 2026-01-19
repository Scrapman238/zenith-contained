#!/usr/bin/env python3
import pexpect
import time
import sys

child = pexpect.spawn(
    "/root/launch",
    encoding="utf-8",
    echo=False,
    timeout=None
)

child.logfile = sys.stdout

child.expect("Select a ZenithProxy platform")
child.sendline("1")

child.expect(">")
child.sendline("y")

child.expect(">")
child.sendline("2")

child.expect(">")
child.sendline("3000")

child.expect(">")
child.sendline("n")

child.expect("ZenithProxy started!")
child.sendline("webApi auth zenith")

time.sleep(0.5)

child.sendcontrol("c")
child.wait()

sys.exit(0)
