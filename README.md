# GLOBALISE IIIF Manifests

- [GLOBALISE IIIF Manifests](#globalise-iiif-manifests)
  - [Introduction](#introduction)
  - [Collections](#collections)
    - [Archive/collection based (`ric-rst:Series` level)](#archivecollection-based-ric-rstseries-level)
    - [Inventory based (`ric-rst:File` level)](#inventory-based-ric-rstfile-level)
    - [Document based (`rico:Record` level)](#document-based-ricorecord-level)
  - [Manifests](#manifests)
    - [Inventory based (`ric-rst:File` level)](#inventory-based-ric-rstfile-level-1)
    - [Document based (`rico:Record` level)](#document-based-ricorecord-level-1)


## Introduction

## Collections

A IIIF Collection allows for the grouping of IIIF Manifests (or other Collections) and their metadata. We have three types of collections:

### Archive/collection based (`ric-rst:Series` level)
A collection of other collections. This can be done for the broadest level (`ric-rst:Fonds`), or for a more specific level (`ric-rst:Series`).

**Question:** should we make collections of collections?

**Example:**
* Archive 1.04.02 (https://www.nationaalarchief.nl/onderzoeken/archief/1.04.02) includes several inventories that are grouped in subcollections (e.g. 'Deel I Heren Zeventien en kamer Amsterdam' or 'Deel I/B RESOLUTIES'). These Collections are grouped together in one Collection.

### Inventory based (`ric-rst:File` level)
Several inventory manifests are grouped together in a collection. This is done for inventories that are part of a (sub)series (`ric-rst:Series`), or share common characteristics.

**Example:**
* Subcollection 'Overgekomen brieven en papieren uit Indië aan de Heren XVII en de kamer Amsterdam. Met inhoudsopgaven' groups the Manifests of inventories (`ric-rst:File`) 1053, 1054 and 1055 together in one Collection. 

### Document based (`rico:Record` level)
Several document-manifests are grouped together in a collection. This is done for documents that are part of a larger whole, such as one inventory number, or other shared characteristics (e.g. same author, subject).

**Example:**
* One inventory number (e.g. '1053 Stukken betreffende de Molukken, Banda, Ambon, Bantam, Makassar en Gresik') is made up of several documents. These documents (via Manifests) are grouped together in one Collection since they are part of the same inventory number.
* All documents (via Manifests) that are written on Bantam in a certain year are grouped together in one Collection.

## Manifests

A IIIF Manifest allows for the grouping of images and their metadata. We generate two types of manifests:

### Inventory based (`ric-rst:File` level)

If we have information on a particular inventory (an instance of `rico:RecordSet`), we generate a manifest for it consisting of all the scans of the documents in that inventory.

**Example:**
* Inventory '8400 Palembang, 1737 apr. 8 - nov. 15; Cheribon, 1737 mrt. 31 - okt. 30 1737' is represented by 208 scans. These scans are grouped together in one Manifest.

### Document based (`rico:Record` level)

If we have information on a particular document, we generate a manifest for it consisting of only the scans of that document.

**Example:**
* Document TANAP-1004 is represented by 9 scans. These scans are grouped together in one Manifest.
