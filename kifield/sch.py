# -*- coding: utf-8 -*-

#
# This code was taken from https://github.com/KiCad/kicad-library-utils/tree/master/sch.
# It's covered by GPL3. Some changes/additions were made by XESS Corp.
#

import sys
import shlex
import re
import os
import sexpdata

from .common import *


sch_field_id_to_name = {
    "0": "reference",
    "1": "value",
    "2": "footprint",
    "3": "datasheet",
}


def unquote(s):
    """Remove any quote marks around a string."""

    if not isinstance(s, basestring):
        return s  # Not a string, so just return it.
    try:
        # This returns inner part of "..." or '...' strings.
        return re.match("^(['\"])(.*)\\1$", s).group(2)
    except (IndexError, AttributeError):
        # No surrounding quotes, so just return string.
        return s


def ensure_quoted(s):
    """
    Returns a quoted version of string 's' if that's not already the case
    """
    rx = r"^\"(.+)\"$"

    if re.match(rx, s) is not None:
        return s
    else:
        return '"{}"'.format(s)


class Description(object):
    """
    A class to parse description information of Schematic Files Format of the KiCad
    TODO: Need to be done, currently just stores the raw data read from file
    """

    def __init__(self, data):
        self.raw_data = data


class Component(object):
    """
    A class to parse components of Schematic Files Format of the KiCad
    """

    _L_KEYS = ["name", "ref"]
    _U_KEYS = ["unit", "convert", "time_stamp"]
    _P_KEYS = ["posx", "posy"]
    _AR_KEYS = ["path", "ref", "part"]
    _F_KEYS = [
        "id",
        "ref",
        "orient",
        "posx",
        "posy",
        "size",
        "attributs",
        "hjust",
        "props",
        "name",
    ]

    _KEYS = {"L": _L_KEYS, "U": _U_KEYS, "P": _P_KEYS, "AR": _AR_KEYS, "F": _F_KEYS}

    def __init__(self, data):
        self.labels = {}
        self.unit = {}
        self.position = {}
        self.references = []
        self.fields = []
        self.old_stuff = []

        for line in data:
            if line[0] == "\t":
                self.old_stuff.append(line)
                continue

            line = line.replace("\n", "")
            s = shlex.shlex(line)
            s.whitespace_split = True
            s.commenters = ""
            s.quotes = '"'
            line = list(s)

            # select the keys list and default values array
            if line[0] in self._KEYS:
                key_list = self._KEYS[line[0]]
                values = line[1:] + [""] * (len(key_list) - len(line[1:]))

            if line[0] == "L":
                self.labels = dict(zip(key_list, values))
            elif line[0] == "U":
                self.unit = dict(zip(key_list, values))
            elif line[0] == "P":
                self.position = dict(zip(key_list, values))
            elif line[0] == "AR":
                self.references.append(dict(zip(key_list, values)))
            elif line[0] == "F":
                self.fields.append(dict(zip(key_list, values)))

    def get_field_names(self):
        """Return the set of all the field names found in a component."""

        field_names = set()
        for f in self.fields:
            try:
                field_names.add(unquote(f["name"]))
            except KeyError:
                pass
        field_names.discard("")
        return field_names

    def get_refs(self):
        """Return a list of references for a component."""

        # Get the references of the component. (There may be more than one
        # if the component is replicated over multiple hierarchical sheets.)
        refs = [r["ref"] for r in self.references]
        refs = [re.search(r'="(.*)"', ref).group(1) for ref in refs]
        refs = set(refs)  # Remove any duplicate references.
        refs.add(self.labels["ref"])  # Non-hierarchical ref.
        return refs

    def add_field(self, field_data):
        """Add a new field to a component."""

        # Start with default field settings.
        field = {
            "id": None,
            "ref": None,
            "orient": "H",
            "posx": "0",
            "posy": "0",
            "size": "50",
            "attributs": "0001",
            "hjust": "C",
            "props": "CNN",
            "name": "~",
        }

        # Merge new field data into default field data.
        field.update(field_data)

        # Make sure ref and name are quoted.
        field["ref"] = ensure_quoted(field["ref"])
        field["name"] = ensure_quoted(field["name"])

        # Set id for new field to be its index in the list of fields.
        field["id"] = str(len(self.fields))

        # Add new field to list of fields.
        self.fields.append(field)

        return field


class Sheet(object):
    """
    A class to parse sheets of Schematic Files Format of the KiCad
    """

    _S_KEYS = ["topLeftPosx", "topLeftPosy", "botRightPosx", "botRightPosy"]
    _U_KEYS = ["uniqID"]
    _F_KEYS = ["id", "value", "IOState", "side", "posx", "posy", "size"]

    _KEYS = {"S": _S_KEYS, "U": _U_KEYS, "F": _F_KEYS}

    def __init__(self, data):
        self.shape = {}
        self.unit = {}
        self.fields = []
        for line in data:
            line = line.replace("\n", "")
            s = shlex.shlex(line)
            s.whitespace_split = True
            s.commenters = ""
            s.quotes = '"'
            line = list(s)
            # select the keys list and default values array
            if line[0] in self._KEYS:
                key_list = self._KEYS[line[0]]
                values = line[1:] + [""] * (len(key_list) - len(line[1:]))
            if line[0] == "S":
                self.shape = dict(zip(key_list, values))
            elif line[0] == "U":
                self.unit = dict(zip(key_list, values))
            elif line[0][0] == "F":
                key_list = self._F_KEYS
                values = line + ["" for n in range(len(key_list) - len(line))]
                self.fields.append(dict(zip(key_list, values)))


class Bitmap(object):
    """
    A class to parse bitmaps of Schematic Files Format of the KiCad
    TODO: Need to be done, currently just stores the raw data read from file
    """

    def __init__(self, data):
        self.raw_data = data


class Schematic(object):
    """
    A class to parse Schematic Files Format of the KiCad
    """

    def __init__(self, filename):
        f = open(filename)
        self.filename = filename
        self.header = f.readline()
        self.libs = []
        self.eelayer = None
        self.description = None
        self.components = []
        self.sheets = []
        self.bitmaps = []
        self.texts = []
        self.wires = []
        self.entries = []
        self.conns = []
        self.noconns = []

        if "EESchema Schematic File" not in self.header:
            self.header = None
            sys.stderr.write("The file is not a KiCad Schematic File\n")
            return

        building_block = False

        while True:
            line = f.readline()
            if not line:
                break

            if line.startswith("LIBS:"):
                self.libs.append(line)

            elif line.startswith("EELAYER END"):
                pass
            elif line.startswith("EELAYER"):
                self.eelayer = line

            elif not building_block:
                if line.startswith("$"):
                    building_block = True
                    block_data = []
                    block_data.append(line)
                elif line.startswith("Text"):
                    data = {"desc": line, "data": f.readline()}
                    self.texts.append(data)
                elif line.startswith("Wire"):
                    data = {"desc": line, "data": f.readline()}
                    self.wires.append(data)
                elif line.startswith("Entry"):
                    data = {"desc": line, "data": f.readline()}
                    self.entries.append(data)
                elif line.startswith("Connection"):
                    data = {"desc": line}
                    self.conns.append(data)
                elif line.startswith("NoConn"):
                    data = {"desc": line}
                    self.noconns.append(data)

            elif building_block:
                block_data.append(line)
                if line.startswith("$End"):
                    building_block = False

                    if line.startswith("$EndDescr"):
                        self.description = Description(block_data)
                    if line.startswith("$EndComp"):
                        self.components.append(Component(block_data))
                    if line.startswith("$EndSheet"):
                        self.sheets.append(Sheet(block_data))
                    if line.startswith("$EndBitmap"):
                        self.bitmaps.append(Bitmap(block_data))

    def get_field_names(self):
        """Return a list all the field names found in a schematic's components."""

        field_names = set(sch_field_id_to_name.values())
        for component in self.components:
            field_names.update(component.get_field_names())
        return list(field_names)

    def save(self, filename=None):
        # check whether it has header, what means that sch file was loaded fine
        if not self.header:
            return

        if not filename:
            filename = self.filename

        # insert the header
        to_write = []
        to_write += [self.header]

        # LIBS
        to_write += self.libs

        # EELAYER
        to_write += [self.eelayer, "EELAYER END\n"]

        # Description
        to_write += self.description.raw_data

        # Sheets
        for sheet in self.sheets:
            to_write += ["$Sheet\n"]
            if sheet.shape:
                line = "S "
                for key in sheet._S_KEYS:
                    line += sheet.shape[key] + " "
                to_write += [line.rstrip() + "\n"]
            if sheet.unit:
                line = "U "
                for key in sheet._U_KEYS:
                    line += sheet.unit[key] + " "
                to_write += [line.rstrip() + "\n"]

            for field in sheet.fields:
                line = ""
                for key in sheet._F_KEYS:
                    line += field[key] + " "
                to_write += [line.rstrip() + "\n"]
            to_write += ["$EndSheet\n"]

        # Components
        for component in self.components:
            to_write += ["$Comp\n"]
            if component.labels:
                line = "L "
                for key in component._L_KEYS:
                    line += component.labels[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.unit:
                line = "U "
                for key in component._U_KEYS:
                    line += component.unit[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.position:
                line = "P "
                for key in component._P_KEYS:
                    line += component.position[key] + " "
                to_write += [line.rstrip() + "\n"]

            for reference in component.references:
                if component.references:
                    line = "AR "
                    for key in component._AR_KEYS:
                        line += reference[key] + " "
                    to_write += [line.rstrip() + "\n"]

            for field in component.fields:
                line = "F "
                for key in component._F_KEYS:
                    line += field[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.old_stuff:
                to_write += component.old_stuff

            to_write += ["$EndComp\n"]

        # Bitmaps
        for bitmap in self.bitmaps:
            to_write += bitmap.raw_data

        # Texts
        for text in self.texts:
            to_write += [text["desc"], text["data"]]

        # Wires
        for wire in self.wires:
            to_write += [wire["desc"], wire["data"]]

        # Entries
        for entry in self.entries:
            to_write += [entry["desc"], entry["data"]]

        # Connections
        for conn in self.conns:
            to_write += [conn["desc"]]

        # No Connetions
        for noconn in self.noconns:
            to_write += [noconn["desc"]]

        to_write += ["$EndSCHEMATC\n"]

        f = open(filename, "w")
        f.writelines(to_write)


def find_by_key(key, array):
    """Return list elements in an array whose first element matches the key."""
    found_elements = []
    for e in array:
        try:
            k = e[0].value().lower()
        except (IndexError, AttributeError, TypeError):
            pass
        else:
            if k == key:
                found_elements.append(e)
    return found_elements
    # return [e for e in array[1:] if e[0].value().lower() == key]


def get_value_by_key(key, array):
    try:
        value = find_by_key(key, array)[0][1]
    except IndexError:
        return None
    else:
        try:
            return value.value()
        except AttributeError:
            return value


class Component_V6(object):
    """
    A class to parse components of Schematic Files Format of the KiCad
    """

    def __init__(self, data, uuid_path=""):
        self.data = data

        # Should be just one lib_id and one uuid.
        self.lib_id = get_value_by_key("lib_id", data)
        self.uuid = get_value_by_key("uuid", data)
        self.uuid_path = "/".join((uuid_path, self.uuid))

        self.fields = []
        for prop in find_by_key("property", data):
            id = get_value_by_key("id", prop)
            self.fields.append({"name": prop[1], "ref": prop[2], "id": id, "prop": prop})

    def get_field_names(self):
        """Return the set of all the field names found in a component."""

        field_names = set()
        for f in self.fields:
            try:
                field_names.add(unquote(f["name"]))
            except KeyError:
                pass
        field_names.discard("")
        return field_names

    def get_refs(self):
        """Return a list of references for a component."""

        refs = []
        for field in self.fields:
            if field["name"] in ("Reference", "Label"):
                refs.append(field["ref"])
        return refs

    def set_field_value(self, name, value):
        for field in self.fields:
            if field['name'] == name:
                field['ref'] = value
                field['prop'][2] = value

    def set_ref(self, ref):
        self.set_field_value('Reference', ref)

    def add_field(self, field_data):
        """Add a new field to a component."""

        # Start with default field settings.
        field = {
            "id": None,
            "ref": None,
            "orient": "H",
            "posx": "0",
            "posy": "0",
            "size": "50",
            "attributs": "0001",
            "hjust": "C",
            "props": "CNN",
            "name": "~",
        }

        # Merge new field data into default field data.
        field.update(field_data)

        # Make sure ref and name are quoted.
        field["ref"] = ensure_quoted(field["ref"])
        field["name"] = ensure_quoted(field["name"])

        # Set id for new field to be its index in the list of fields.
        field["id"] = str(len(self.fields))

        # Add new field to list of fields.
        self.fields.append(field)

        return field


class Sheet_V6(object):
    """
    A class to parse sheets of Schematic Files Format of the KiCad
    """

    def __init__(self, data, parent_filename, uuid_path):
        self.uuid = get_value_by_key("uuid", data)
        self.uuid_path = "/".join((uuid_path, self.uuid))

        properties = find_by_key("property", data)
        for property in properties:
            if property[1].lower() == "sheet file":
                self.filename = property[2]
                if not os.path.isabs(self.filename):
                    parent_dir = os.path.dirname(parent_filename)
                    self.filename = os.path.join(parent_dir, self.filename)
                break


class Schematic_V6(object):
    """
    A class to parse KiCad V6 schematic files.
    """

    def __init__(self, filename, uuid_path=""):

        # Parse the schematic file into a nested list.
        with open(filename) as fp:
            try:
                self.sexpdata = sexpdata.loads("\n".join(fp.readlines()))
            except AssertionError:
                sys.stderr.write("The file is not a KiCad Schematic File\n")
                return

        self.filename = filename
        self.description = None

        # Parse any hierarchical subsheets.
        self.children = []
        child_sheets = [
            Sheet_V6(sheet, filename, uuid_path)
            for sheet in find_by_key("sheet", self.sexpdata)
        ]
        for sheet in child_sheets:
            self.children.append(self.__class__(sheet.filename, sheet.uuid_path))

        # Get any components included in this schematic file.
        self.local_components = [
            Component_V6(comp, uuid_path)
            for comp in find_by_key("symbol", self.sexpdata)
        ]

        # The total list of components includes the local components plus the
        # total components of each subsheet.
        self.components = self.local_components[:]
        for child in self.children:
            self.components.extend(child.components)

        # If this schematic has a list of symbol instances, then use it to set the
        # references for each instantiated component.
        self.uuid_path_refs = {}
        try:
            comp_insts = find_by_key("symbol_instances", self.sexpdata)[0]
        except (TypeError, IndexError):
            pass
        else:
            for inst in find_by_key("path", comp_insts):
                inst_uuid_path = inst[1]
                inst_ref = get_value_by_key("reference", inst)
                self.uuid_path_refs[inst_uuid_path] = inst_ref
            for component in self.components:
                component.set_ref(self.uuid_path_refs[component.uuid_path])

    def get_field_names(self):
        """Return a list all the field names found in a schematic's components."""

        # Add names of fields every component will have.
        field_names = set(sch_field_id_to_name.values())

        # Add any extra field names from each component.
        for component in self.components:
            field_names.update(component.get_field_names())

        return list(field_names)

    def save(self, filename=None):

        def indent(s):
            out_s = ''
            tab = '    '
            indent = ''
            nl = ''
            in_quote = False
            backslash = False

            for c in s:
                if c == '(' and not in_quote:
                    out_s += nl + indent
                    nl = '\n'
                    indent += tab
                elif c ==')' and not in_quote:
                    indent = indent[len(tab):]
                elif c == '"' and not backslash:
                    in_quote = not in_quote
                
                if c == '\\':
                    backslash = True
                else:
                    backslash = False

                out_s += c
            
            return out_s

        with open(filename, "w") as fp:
            fp.write(indent(sexpdata.dumps(self.sexpdata)))
        return

        # check whether it has header, what means that sch file was loaded fine
        if not self.header:
            return

        if not filename:
            filename = self.filename

        # insert the header
        to_write = []
        to_write += [self.header]

        # LIBS
        to_write += self.libs

        # EELAYER
        to_write += [self.eelayer, "EELAYER END\n"]

        # Description
        to_write += self.description.raw_data

        # Sheets
        for sheet in self.sheets:
            to_write += ["$Sheet\n"]
            if sheet.shape:
                line = "S "
                for key in sheet._S_KEYS:
                    line += sheet.shape[key] + " "
                to_write += [line.rstrip() + "\n"]
            if sheet.unit:
                line = "U "
                for key in sheet._U_KEYS:
                    line += sheet.unit[key] + " "
                to_write += [line.rstrip() + "\n"]

            for field in sheet.fields:
                line = ""
                for key in sheet._F_KEYS:
                    line += field[key] + " "
                to_write += [line.rstrip() + "\n"]
            to_write += ["$EndSheet\n"]

        # Components
        for component in self.components:
            to_write += ["$Comp\n"]
            if component.labels:
                line = "L "
                for key in component._L_KEYS:
                    line += component.labels[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.unit:
                line = "U "
                for key in component._U_KEYS:
                    line += component.unit[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.position:
                line = "P "
                for key in component._P_KEYS:
                    line += component.position[key] + " "
                to_write += [line.rstrip() + "\n"]

            for reference in component.references:
                if component.references:
                    line = "AR "
                    for key in component._AR_KEYS:
                        line += reference[key] + " "
                    to_write += [line.rstrip() + "\n"]

            for field in component.fields:
                line = "F "
                for key in component._F_KEYS:
                    line += field[key] + " "
                to_write += [line.rstrip() + "\n"]

            if component.old_stuff:
                to_write += component.old_stuff

            to_write += ["$EndComp\n"]

        # Bitmaps
        for bitmap in self.bitmaps:
            to_write += bitmap.raw_data

        # Texts
        for text in self.texts:
            to_write += [text["desc"], text["data"]]

        # Wires
        for wire in self.wires:
            to_write += [wire["desc"], wire["data"]]

        # Entries
        for entry in self.entries:
            to_write += [entry["desc"], entry["data"]]

        # Connections
        for conn in self.conns:
            to_write += [conn["desc"]]

        # No Connetions
        for noconn in self.noconns:
            to_write += [noconn["desc"]]

        to_write += ["$EndSCHEMATC\n"]

        f = open(filename, "w")
        f.writelines(to_write)

