import json
import os
from collections import defaultdict
from dataclasses import dataclass, field

import iiif_prezi3
import requests
from lxml import etree as ET

from dotenv import load_dotenv


iiif_prezi3.config.configs["helpers.auto_fields.AutoLang"].auto_lang = "en"

# read from .env file
load_dotenv()
TEXTREPO_API_URL = os.getenv("TEXTREPO_API_URL", "")
TEXTREPO_API_KEY = os.getenv("TEXTREPO_API_KEY", "")


@dataclass(kw_only=True)
class Base:
    code: str
    title: str


@dataclass(kw_only=True)
class Collection(Base):
    hasPart: list = field(default_factory=list)
    uri: str = field(default_factory=str)

    def files(self, use_filegroup=False):
        for i in self.hasPart:
            if use_filegroup and isinstance(i, FileGroup):
                yield i
            elif isinstance(i, File):
                yield i
            else:
                yield from i.files()


@dataclass(kw_only=True)
class Fonds(Collection):
    pass


@dataclass(kw_only=True)
class Series(Collection):
    pass


@dataclass(kw_only=True)
class FileGroup(Collection):
    date: str


@dataclass(kw_only=True)
class File(Base):
    uri: str
    date: str
    metsid: str


def to_collection(
    i: Fonds | Series | FileGroup, base_url: str, prefix="", base_url_manifests=""
):
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
                base_url_manifests=base_url_manifests,
            )

        elif isinstance(c, FileGroup):
            sub_part = to_collection(
                c,
                base_url,
                prefix=collection_filename.replace(".json", "/"),
                base_url_manifests=base_url_manifests,
            )  # or manifest?
        elif isinstance(c, File):
            if base_url_manifests:
                sub_part = to_manifest(
                    c,
                    base_url_manifests,
                    prefix="inventories/",
                )
            else:
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
    i: File | dict,
    base_url: str,
    prefix="",
    license_uri="https://creativecommons.org/publicdomain/mark/1.0/",
    fetch_from_url=False,
    hwd_data: dict = None,
):
    if isinstance(i, File):
        manifest_filename = f"{prefix}{i.code}.json"
        manifest_filename = manifest_filename.replace(" ", "+")
        manifest_id = base_url + manifest_filename

        # If file already exists, skip
        if os.path.exists(manifest_filename):
            # return Reference (shallow) only
            return iiif_prezi3.Reference(
                id=manifest_id,
                label=f"{i.code} - {i.title}",
                type="Manifest",
            )

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

    elif isinstance(i, dict):
        print("Making manifest for inventory", i["code"])
        manifest_filename = f"{prefix}{i['code']}.json"
        manifest_id = base_url + manifest_filename

        # If file already exists, skip
        if os.path.exists(manifest_filename):
            return

        os.makedirs(os.path.dirname(manifest_filename), exist_ok=True)

        if "inventories" in prefix:
            label = f"Inventory {i['code']}"
        else:
            label = i["titles"][0]

        manifest = iiif_prezi3.Manifest(
            id=manifest_id,
            label=label,
            metadata=[
                iiif_prezi3.KeyValueString(
                    label="Identifier",
                    value={"en": [i["code"]]},
                ),
                iiif_prezi3.KeyValueString(
                    label="Titles",
                    value={"en": [t if t else "?" for t in i["titles"]]},
                ),
                iiif_prezi3.KeyValueString(
                    label="Dates",
                    value={"en": [d if d else "?" for d in i["dates"]]},
                ),
                iiif_prezi3.KeyValueString(
                    label="Permalink",
                    value={
                        "en": [
                            f'<a href="{u}">{u}</a>' if u else "?" for u in i["uris"]
                        ]
                    },
                ),
            ],
            # seeAlso={"id": i.uri, "label": "Permalink"},
            rights=license_uri,
        )

        if "scans" in i and i["scans"]:
            scans = i["scans"]
        else:
            scans = get_scans(i["metsid"])
    else:
        raise TypeError("i should be a File or dict")

    # Add scans
    for n, (file_name, iiif_service_info) in enumerate(scans, 1):
        if file_name.endswith((".tif", ".tiff", ".jpg", ".jpeg")):
            base_file_name = file_name.rsplit(".", 1)[0]
        else:
            base_file_name = file_name

        if hwd_data and base_file_name in hwd_data:
            height = hwd_data[base_file_name]["h"]
            width = hwd_data[base_file_name]["w"]
        elif hwd_data:
            print(f"Missing height and width for {base_file_name}")
            fetch_from_url = True
        else:
            height = 100
            width = 100

        if fetch_from_url:
            try:
                manifest.make_canvas_from_iiif(
                    url=iiif_service_info,
                    id=f"{manifest_id}/canvas/p{n}",
                    label=base_file_name,
                    anno_id=f"{manifest_id}/canvas/p{n}/anno",
                    anno_page_id=f"{manifest_id}/canvas/p{n}/annotationpage",
                )
            except:
                fetch_from_url = False
                height = 100
                width = 100

        if not fetch_from_url:
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
                height=height,
                width=width,
            )

            canvas = iiif_prezi3.Canvas(
                id=canvas_id,
                label=base_file_name,
                height=height,
                width=width,
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
            mets = ET.parse(os.path.join(cache_path, metsid + ".xml"))
        else:
            url = "https://service.archief.nl/gaf/api/mets/v1/" + metsid
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
        series_code = series_code.replace("/", "-")
    else:
        series_code = series_title

    s = Series(code=series_code, title=series_title)

    parts = get_file_and_filegrp_els(series_el, filter_codes=filter_codes)
    s.hasPart += parts

    return s


def get_file_and_filegrp_els(series_el, filter_codes: set = set()):
    parts = []

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
            parts.append(i)

    return parts


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
    )

    parts = get_file_and_filegrp_els(filegrp_el, filter_codes=filter_codes)
    filegrp.hasPart += parts

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
    title = "".join(did.find("unittitle").itertext()).strip()
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
    )

    return f


def parse_csv(csv_file_path: str, sep=",", encoding="utf-8"):
    import pandas as pd

    df = pd.read_csv(csv_file_path, sep=sep, encoding=encoding)

    # document_id	internal_id	title	year_creation_or_dispatch	inventory_number	folio_or_page	folio_or_page_range	scan_range	scan_start	scan_end	no_of_scans	no_of_pages	GM_id	remarks

    data = defaultdict(lambda: defaultdict(list))
    for _, d in df.iterrows():
        data[d.document_id]["titles"].append(d.title)
        data[d.document_id]["dates"].append(d.year_creation_or_dispatch)
        # data[d.document_id]["uris"].append(f.uri)
        # data[d.document_id]["metsid"] = f.metsid

        filenames = []
        scan_name, scan_name_start_index = d.scan_start.rsplit("_", 1)

        scan_name = scan_name.split("/file/")[1]
        scan_name_start_index = int(scan_name_start_index)

        scan_name_end_index = scan_name_start_index + d.no_of_scans - 1  # inclusive

        for i in range(scan_name_start_index, scan_name_end_index + 1):
            filenames.append(f"{scan_name}_{str(i).zfill(4)}")

        data[d.document_id]["scans"] = get_iiif_urls_from_textrepo(filenames)

    return data


def get_iiif_urls_from_textrepo(filesnames: list[str]) -> list[tuple[str, str]]:
    from textrepo.client import TextRepoClient

    client = TextRepoClient(base_uri=TEXTREPO_API_URL, api_key=TEXTREPO_API_KEY)

    scans = []
    for filename in filesnames:
        document_metadata = client.find_document_metadata(external_id=filename)
        scan_url = document_metadata["scan_url"]

        service_info_url = scan_url.replace("/iip/", "/iipsrv?IIIF=/") + "/info.json"

        scans.append((filename, service_info_url))

    return scans


def main(
    ead_file_path: str = "",
    csv_file_path: str = "",
    base_url_collections: str = "https://example.org/",
    base_url_manifests: str = "https://example.org/",
    filter_codes_path: str = "",
    hwd_data_path: str = "",
) -> None:
    """
    Generate IIIF Collections and Manifests from an EAD file.

    Args:
        ead_file_path (str): Path to the EAD file.
        base_url (str): Base URL for the manifests.
        filter_codes_path (str, optional): Path to a JSON file with a list of inventory numbers to include. Defaults to "".
        hwd_data_path (str, optional): Path to a JSON file with the height and width of each scan. Defaults to "".

    Returns:
        None
    """

    if filter_codes_path:
        with open(filter_codes_path, "r") as infile:
            globalise_selection = set(json.load(infile))
    else:
        globalise_selection = []

    if hwd_data_path:
        if hwd_data_path.endswith(".gz"):
            import gzip

            with gzip.open(hwd_data_path, "r") as infile:
                hwd_data = json.load(infile)
        else:
            with open(hwd_data_path, "r") as infile:
                hwd_data = json.load(infile)
    else:
        hwd_data = None

    if ead_file_path:
        # Parse EAD, filter on relevant inventory numbers
        fonds = parse_ead(ead_file_path, filter_codes=globalise_selection)

        # Generate IIIF Manifests from inventory numbers (unique)
        data = defaultdict(lambda: defaultdict(list))
        for f in fonds.files():
            data[f.code]["titles"].append(f.title)
            data[f.code]["dates"].append(f.date)
            data[f.code]["uris"].append(f.uri)
            data[f.code]["metsid"] = f.metsid

        for code, metadata in data.items():
            metadata["code"] = code
            to_manifest(metadata, base_url_manifests, "inventories/", hwd_data=hwd_data)

        # Generate IIIF Collections and Manifests from hierarchy
        to_collection(
            fonds, base_url_collections, base_url_manifests=base_url_manifests
        )

    elif csv_file_path:
        data = parse_csv(csv_file_path)

        for code, metadata in data.items():
            metadata["code"] = code
            to_manifest(metadata, base_url_manifests, "documents/", hwd_data=hwd_data)

    else:
        raise ValueError("Either ead_file_path or csv_file_path should be given")


if __name__ == "__main__":
    # Inventories
    main(
        ead_file_path="data/1.04.02.xml",
        # csv_file_path="data/document_metadata_july_2023.csv",
        base_url_manifests="https://data.globalise.huygens.knaw.nl/manifests/",
        base_url_collections="https://data.globalise.huygens.knaw.nl/collections/",
        filter_codes_path="data/globalise_htr_selection.json",
        hwd_data_path="data/1.04.02_hwd.json.gz",
    )

    # Documents
    main(
        # ead_file_path="data/1.04.02.xml",
        csv_file_path="data/document_metadata_july_2023.csv",
        base_url_manifests="https://data.globalise.huygens.knaw.nl/manifests/",
        # filter_codes_path="data/globalise_htr_selection.json",
        # hwd_data_path="data/1.04.02_hwd.json.gz",
    )
