#!/usr/bin/env python3
# Use this script to update/regenerate the layouts strings in pelita.layouts.py

import base64
from pathlib import Path
import zlib

import pelita

EXTENSION = '.layout'
OUTFILENAME = '__layouts.py'

local_dir = Path(__file__).resolve().parent
pelita_path = Path(pelita.__file__).parent
outfile = pelita_path / OUTFILENAME

layout_entry = '{name} = """{code}"""\n'

content = '### This file is auto-generated. DO NOT EDIT! ###\n'
# loop through all layout files
for f in sorted(local_dir.iterdir()):
    flname, ext = f.stem, f.suffix
    if ext != EXTENSION:
        continue
    layout = f.read_bytes()

    layout_name = "layout_" + flname
    # encode layout string
    layout_code = base64.encodebytes(zlib.compress(layout)).decode()

    content += layout_entry.format(name=layout_name, code=layout_code)

# write out file in pelita directory
with open(outfile, 'w') as out:
    out.write(content)
