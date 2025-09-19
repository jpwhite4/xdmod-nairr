"""
csv_json_builder.py

This script connects to a Postgres database and extracts configuration and mapping data required for XDMoD (XD Metrics on Demand) NAIRR (National AI Research Resource) integration and reporting.

It generates several configuration files in JSON and CSV formats, using SQL queries to gather information about organizations, users, projects, field of science (FOS) hierarchies, group-to-hierarchy mappings, and cloud project-to-PI mappings. These files are saved to the XDMoD configuration directory, typically located at /data/www/xdmod/etc.

Specifically, this script:
- Reads database connection details from portal_settings.ini.
- Queries the database for:
    - Organization information (organization.json)
    - User and project PI information (names.csv)
    - Field of Science hierarchies (hierarchy.csv)
    - Group-to-hierarchy mapping (group-to-hierarchy.csv)
    - Cloud project to PI mapping (cloud-project-to-pi.csv)
- Writes these outputs in the expected format for XDMoD ingestion and configuration.

This script is intended for use in the XDMoD NAIRR deployment workflow as part of automated configuration and data refreshes.
"""

org_sql = """
SELECT
  TRIM(o.organization_name) AS "name",
  TRIM(
    COALESCE(o.organization_abbr, o.organization_name)
  ) AS "abbr"
FROM
  xras.organizations o
  JOIN xras.allocations_processes ap ON ap.allocations_process_id = o.allocations_process_id
WHERE
  ap.allocations_process_name_abbr = 'NAIRR'
  AND o.is_reconciled IS TRUE
ORDER BY
  "name" ASC;
"""


names_sql = """
SELECT
  username AS orcid,
  first_name,
  middle_name,
  last_name,
  TRIM(
    COALESCE(o.organization_abbr, o.organization_name)
  ) AS "organization_name"
FROM
  xras.people p
  JOIN xras.organizations o ON o.organization_id = p.organization_id
  JOIN xras.allocations_processes ap ON ap.allocations_process_id = o.allocations_process_id
WHERE
  ap.allocations_process_name_abbr = 'NAIRR'
ORDER BY
  p.person_id ASC;
"""

nairr_project_sql = """
WITH
  RankedRequests AS (
    SELECT
      username AS orcid,
      first_name,
      middle_name,
      last_name,
      TRIM(
        COALESCE(o.organization_abbr, o.organization_name)
      ) AS "organization_name",
      rpr.request_role_type_id,
      r.request_master_id,
      rm.request_number AS "nairr_project_name",
      p.person_id,
      r.date_submitted,
      ROW_NUMBER() OVER (
        PARTITION BY
          rm.request_number
        ORDER BY
          rpr.begin_date DESC
      ) AS row_rank
    FROM
      xras.people p
      JOIN xras.organizations o ON o.organization_id = p.organization_id
      JOIN xras.request_people_roles rpr ON p.person_id = rpr.person_id
      JOIN xras.requests r ON r.request_id = rpr.request_id
      JOIN xras.request_masters rm ON r.request_master_id = rm.request_master_id
      JOIN xras.request_role_types rtt ON rpr.request_role_type_id = rtt.request_role_type_id
      JOIN xras.allocations_processes ap ON ap.allocations_process_id = o.allocations_process_id
    WHERE
      ap.allocations_process_name_abbr = 'NAIRR'
      AND rtt.request_role_type = 'PI'
      AND rm.request_number IS NOT NULL
  )
SELECT
  *
FROM
  RankedRequests
WHERE
  row_rank = 1
ORDER BY
  person_id ASC;
"""

hierarchy_sql = """
select
  ft1.fos_name,
  ft1.fos_type_parent_id,
  parent_ft.fos_name as parent_name
from
  xras.fos_types ft1
  LEFT JOIN xras.fos_types parent_ft ON parent_ft.fos_type_id = ft1.fos_type_parent_id
WHERE
  ft1.allocations_process_id = 108
ORDER By
  parent_name DESC;
"""

groups_sql = """
SELECT
  rm.request_number AS "nairr_project_name",
  r.request_id,
  rft.fos_type_id,
  ft.fos_name
FROM
  xras.requests r
  JOIN xras.request_masters rm ON rm.request_master_id = r.request_master_id
  JOIN xras.request_fos_types rft ON rft.request_id = r.request_id
  JOIN xras.fos_types ft ON ft.fos_type_id = rft.fos_type_id
WHERE
  ft.allocations_process_id = 108
  AND rm.request_number IS NOT NULL
ORDER BY
  rm.request_number ASC;
"""

cloud_sql = """
select distinct
  res.resource_name as resource_name,
  rm.request_number
from
  xras.resources res
  join xras.action_resources ar on res.resource_id = ar.resource_id
  join xras.actions a on ar.action_id = a.action_id
  join xras.requests r on a.request_id = r.request_id
  join xras.request_masters rm on r.request_master_id = rm.request_master_id
where
  rm.allocations_process_id = 108
  and res.production_begin_date is not null
  and rm.request_number is not null
  and resource_name in ('Indiana Jetstream2 GPU')
"""
import configparser
import csv
import json
import psycopg2
import re

XDMOD_CONFIG_PATH = "/data/www/xdmod/etc"


def save_json(filename, data):
    with open(f"{XDMOD_CONFIG_PATH}/{filename}", "w") as filep:
        json.dump(data, filep, indent=4)


def save_csv(filename, data, quoting=csv.QUOTE_MINIMAL):
    with open(filename, "w") as f:
        write = csv.writer(f, quoting=quoting)
        write.writerows(data)


def fetch_and_append(cur, query, process_row_func, target_list):
    cur.execute(query)
    for row in cur:
        processed_row = process_row_func(row)
        target_list.append(processed_row)


def demangle_name(inname):

    name = inname
    r = re.compile(r"^([^(]+)")
    mtch = r.match(name)
    if mtch:
        name = mtch.group(0)

    return re.sub(r"[^\w]", "-", name)


def fetch_and_append_cloud(cur, query, process_row_func, target_list):
    cur.execute(query)
    for row in cur:
        processed_row = process_row_func(row)
        processed_row[2] = demangle_name(processed_row[2])
        target_list.append(processed_row)


def org_builder(cur, query, org_list):
    cur.execute(query)
    for data in cur:
        org = {
            "name": data[0],
            "abbrev": data[1],
        }
        if org not in org_list:
            org_list.append(org)


def main():

    config = configparser.ConfigParser()
    config.read(f"{XDMOD_CONFIG_PATH}/portal_settings.d/nairr.ini")

    orgs = []
    names = []
    fos_list = []
    groups = []
    cloud_to_pi = []

    db_config = {
        "database": config["tgcdbmirror"]["database"].strip("'"),
        "host": config["tgcdbmirror"]["host"].strip("'"),
        "user": config["tgcdbmirror"]["user"].strip("'"),
        "password": config["tgcdbmirror"]["pass"].strip("'"),
        "port": config["tgcdbmirror"]["port"].strip("'"),
    }

    with open(f"{XDMOD_CONFIG_PATH}/organization.json", "r") as org_file:
        for org in json.load(org_file):
            orgs.append(org)
    with psycopg2.connect(**db_config) as conn:

        with conn.cursor() as cur:
            # Organization.json
            org_builder(cur, org_sql, orgs)

            # users for names.csv
            fetch_and_append(
                cur, names_sql, lambda row: [row[0], row[1], row[3], row[4]], names
            )
            # nairr_projects for names.csv
            fetch_and_append(
                cur,
                nairr_project_sql,
                lambda row: [row[7], row[1], row[3], row[4]],
                names,
            )

            # group to field of science for group-to-hiearchy.csv
            fetch_and_append(cur, groups_sql, lambda row: [row[0], row[3]], groups)

            # fos hieararchy for hierarchy.csv
            fetch_and_append(
                cur, hierarchy_sql, lambda row: [row[0], row[0], row[2] or ""], fos_list
            )

            fetch_and_append_cloud(
                cur,
                cloud_sql,
                lambda row: [row[1], row[1], row[0]],
                cloud_to_pi,
            )

        save_json("organization.json", orgs)

        save_csv("names.csv", names)

        save_csv("group-to-hierarchy.csv", groups, csv.QUOTE_ALL)

        save_csv("hierarchy.csv", fos_list, csv.QUOTE_ALL)

        save_csv("cloud-project-to-pi.csv", cloud_to_pi)


if __name__ == "__main__":
    main()
