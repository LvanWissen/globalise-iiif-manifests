import json
import os
from dataclasses import dataclass, field

import iiif_prezi3
import requests
from lxml import etree as ET

iiif_prezi3.config.configs["helpers.auto_fields.AutoLang"].auto_lang = "en"


@dataclass
class Fonds:
    code: str
    title: str
    uri: str
    hasPart: list


@dataclass
class Series:
    code: str
    title: str
    uri: str
    hasPart: list


@dataclass
class FileGroup:
    code: str
    title: str
    date: str
    hasPart: list
    uri: str = field(default_factory=str)


@dataclass
class File:
    code: str
    title: str
    uri: str
    date: str
    metsid: str
    hasPart: list


@dataclass
class Document:
    code: str
    title: str
    uri: str
    date: str


def to_collection(i: Fonds | Series | FileGroup, base_url: str, prefix=""):
    collection_filename = f"{prefix}{i.code}.json"
    collection_filename = collection_filename.replace(" ", "+")
    collection_id = base_url + collection_filename

    dirname = os.path.dirname(collection_filename)

    collection = iiif_prezi3.Collection(id=collection_id, label=f"{i.code} - {i.title}")

    metadata = [
        iiif_prezi3.KeyValueString(
            label="Identifier",
            value={"en": [i.code]},
        ),
        iiif_prezi3.KeyValueString(
            label="Title",
            value={"en": [i.title]},
        ),
    ]

    if i.uri:
        metadata.append(
            iiif_prezi3.KeyValueString(
                label="Permalink",
                value={"en": [f'<a href="{i.uri}">{i.uri}</a>']},
            )
        )

    at_least_one_file = False
    for c in i.hasPart:
        if isinstance(c, Series):
            sub_part = to_collection(
                c,
                base_url,
                prefix=collection_filename.replace(".json", "/"),
            )

        elif isinstance(c, FileGroup):
            sub_part = to_collection(
                c,
                base_url,
                prefix=collection_filename.replace(".json", "/"),
            )  # or manifest?
        elif isinstance(c, File):
            sub_part = to_manifest(
                c,
                base_url,
                prefix=collection_filename.replace(".json", "/"),
            )

        # Recursively add sub-collections and manifests if there is at least one file
        if sub_part:
            at_least_one_file = True
            collection.add_item(sub_part)

    if at_least_one_file:
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        with open(collection_filename, "w") as outfile:
            outfile.write(collection.json(indent=2))

        return collection
    else:
        return None


def to_manifest(
    i: File,
    base_url: str,
    prefix="",
    license_uri="https://creativecommons.org/publicdomain/mark/1.0/",
    fetch_from_url=False,
):
    manifest_filename = f"{prefix}{i.code}.json"
    manifest_filename = manifest_filename.replace(" ", "+")
    manifest_id = base_url + manifest_filename

    os.makedirs(os.path.dirname(manifest_filename), exist_ok=True)

    manifest = iiif_prezi3.Manifest(
        id=manifest_id,
        label=f"{i.code} - {i.title}",
        metadata=[
            iiif_prezi3.KeyValueString(
                label="Identifier",
                value={"en": [i.code]},
            ),
            iiif_prezi3.KeyValueString(
                label="Title",
                value={"en": [i.title]},
            ),
            iiif_prezi3.KeyValueString(
                label="Date",
                value={"en": [i.date or "?"]},
            ),
            iiif_prezi3.KeyValueString(
                label="Permalink",
                value={"en": [f'<a href="{i.uri}">{i.uri}</a>']},
            ),
        ],
        # seeAlso={"id": i.uri, "label": "Permalink"},
        rights=license_uri,
    )
    scans = get_scans(i.metsid)

    for n, (file_name, iiif_service_info) in enumerate(scans, 1):
        if fetch_from_url:
            manifest.make_canvas_from_iiif(
                url=iiif_service_info,
                id=f"{manifest_id}/canvas/p{n}",
                label=file_name,
                anno_id=f"{manifest_id}/canvas/p{n}/anno",
                anno_page_id=f"{manifest_id}/canvas/p{n}/annotationpage",
            )
        else:
            canvas_id = f"{manifest_id}/canvas/p{n}"

            service_id = iiif_service_info.replace("/info.json", "")

            anno_id = f"{manifest_id}/canvas/p{n}/anno"
            anno_page_id = f"{manifest_id}/canvas/p{n}/annotationpage"

            service = iiif_prezi3.ServiceItem1(
                id=service_id,
                profile="http://iiif.io/api/image/2/level1.json",
                type="ImageService2",
            )

            body_id = f"{service_id}/full/full/0/default.jpg"
            body = iiif_prezi3.ResourceItem(
                id=body_id,
                type="Image",
                service=[service],
                format="image/jpeg",
                height=100,  # mock value for now
                width=100,  # mock value for now
            )

            canvas = iiif_prezi3.Canvas(
                id=canvas_id,
                label=file_name,
                height=100,  # mock value for now
                width=100,  # mock value for now
            )
            annotation = iiif_prezi3.Annotation(
                id=anno_id,
                motivation="painting",
                body=body,
                target=canvas.id,
            )

            annotationPage = iiif_prezi3.AnnotationPage(id=anno_page_id)
            annotationPage.add_item(annotation)

            canvas.add_item(annotationPage)

            manifest.add_item(canvas)

    with open(manifest_filename, "w") as outfile:
        outfile.write(manifest.json(indent=2))

    return manifest


def get_scans(metsid: str, cache_path="data/gaf/") -> list[tuple[str, str]]:
    NS = {"mets": "http://www.loc.gov/METS/"}

    scans = []

    if metsid:
        if cache_path and metsid + ".xml" in os.listdir(cache_path):
            print(f"Fetching {metsid} from cache")
            mets = ET.parse(os.path.join(cache_path, metsid + ".xml"))
        else:
            url = "https://service.archief.nl/gaf/api/mets/v1/" + metsid
            print("Fetching", url)
            xml = requests.get(url).text
            mets = ET.fromstring(bytes(xml, encoding="utf-8"))

            if cache_path:
                with open(os.path.join(cache_path, metsid + ".xml"), "w") as outfile:
                    outfile.write(xml)

        for file_el in mets.findall(
            "mets:fileSec/mets:fileGrp[@USE='DISPLAY']/mets:file",
            namespaces=NS,
        ):
            file_id = file_el.attrib["ID"][:-3]  # without IIP
            service_info_url = file_el.find(
                "./mets:FLocat[@LOCTYPE='URL']",
                namespaces=NS,
            ).attrib["{http://www.w3.org/1999/xlink}href"]

            service_info_url = service_info_url.replace("/iip/", "/iipsrv?IIIF=/")

            file_name = (
                mets.find(
                    "mets:structMap/mets:div/mets:div[@ID='" + file_id + "']",
                    namespaces=NS,
                )
                .attrib["LABEL"]
                .split("/")[-1]
            )

            scans.append((file_name, service_info_url))

    return scans


def parse_ead(ead_file_path: str, filter_codes: set = set()) -> Fonds:
    tree = ET.parse(ead_file_path)

    fonds_code = tree.find("eadheader/eadid").text
    fonds_title = tree.find("eadheader/filedesc/titlestmt/titleproper").text
    permalink = tree.find("eadheader/eadid[@url]").attrib["url"]

    fonds = Fonds(
        code=fonds_code,
        title=fonds_title,
        uri=permalink,
        hasPart=[],
    )

    series_els = tree.findall(".//c[@level='series']")
    for series_el in series_els:
        s = get_series(series_el, filter_codes=filter_codes)
        fonds.hasPart.append(s)

    return fonds


def get_series(series_el, filter_codes: set = set()) -> Series:
    series_code_el = series_el.find("did/unitid[@type='series_code']")
    series_title = "".join(series_el.find("did/unittitle").itertext()).strip()

    while "  " in series_title:  # double space
        series_title = series_title.replace("  ", " ")

    if series_code_el is not None:
        series_code = series_code_el.text
        series_code = series_code.replace("/", "")
    else:
        series_code = series_title

    s = Series(
        code=series_code,
        title=series_title,
        uri="",
        hasPart=[],
    )

    file_and_filegrp_els = series_el.xpath("child::*")
    for el in file_and_filegrp_els:
        if el.get("level") == "file":
            i = get_file(el, filter_codes)

        elif el.get("otherlevel") == "filegrp":
            i = get_filegrp(el, filter_codes)

        elif el.get("level") == "subseries":
            i = get_series(el, filter_codes)
        else:
            continue

        if i:
            s.hasPart.append(i)

    return s


def get_filegrp(filegrp_el, filter_codes: set = set()) -> FileGroup:
    filegrp_code = filegrp_el.find("did/unitid").text

    # Title
    filegrp_title = "".join(filegrp_el.find("did/unittitle").itertext()).strip()
    while "  " in filegrp_title:  # double space
        filegrp_title = filegrp_title.replace("  ", " ")

    # Date
    date_el = filegrp_el.find("did/unitdate")
    if date_el is not None:
        date = date_el.attrib.get("normal", date_el.attrib.get("text"))
    else:
        date = ""

    filegrp = FileGroup(
        code=filegrp_code,
        title=filegrp_title,
        date=date,
        hasPart=[],
    )

    file_els = filegrp_el.findall("c[@level='file']")
    for file_el in file_els:
        f = get_file(file_el, filter_codes)

        if f:
            filegrp.hasPart.append(f)

    return filegrp


def get_file(file_el, filter_codes: set = set()) -> File | None:
    did = file_el.find("did")

    # Inventory number
    inventorynumber_el = did.find("unitid[@identifier]")
    if inventorynumber_el is not None:
        inventorynumber = inventorynumber_el.text
    else:
        return None

    # Filter on selection
    if filter_codes and inventorynumber not in filter_codes:
        return None

    # URI
    permalink = did.find("unitid[@type='handle']").text

    # Title
    title = "".join(did.find("unittitle").itertext())
    while "  " in title:  # double space
        title = title.replace("  ", " ")

    # Date
    date_el = did.find("unittitle/unitdate")
    if date_el is not None:
        date = date_el.attrib.get("normal", date_el.attrib.get("text"))
    else:
        date = ""

    # METS id
    metsid_el = did.find("dao")
    if metsid_el is not None:
        metsid = metsid_el.attrib["href"].split("/")[-1]
    else:
        metsid = ""

    f = File(
        code=inventorynumber,
        title=title,
        uri=permalink,
        date=date,
        metsid=metsid,
        hasPart=[],
    )

    return f


def main(
    ead_file_path: str,
    base_url: str,
    filter_codes_path: str = "",
) -> None:
    """
    Generate IIIF Collections and Manifests from an EAD file.

    The lowest level of these collections are manifests for each inventory.

    Args:
        ead_file_path (str): File path to the EAD file of a specific archive
        collection_number (str): The collection number of this archive
        collection_label (str): The title of this archive
        collection_permalink (str): The permalink of this archive (e.g. handle)
        base_url (str): The base URL of the IIIF manifests and collections
    """

    if filter_codes_path:
        with open(filter_codes_path, "r") as infile:
            globalise_selection = set(json.load(infile))
    else:
        globalise_selection = []

    # Parse EAD, filter on relevant inventory numbers
    fonds = parse_ead(ead_file_path, filter_codes=globalise_selection)

    # Generate IIIF Collections and Manifests from hierarchy
    to_collection(fonds, base_url)


if __name__ == "__main__":
    main(
        ead_file_path="data/1.04.02.xml",
        base_url="https://globalise-huygens.github.io/iiif-manifests/",
        filter_codes_path="data/globalise_htr_selection.json",
    )
