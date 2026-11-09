"""SQL that turns raw ClinicalTrials.gov studies (nct_id + JSON sections) into FLAT tables only.
Adapted from ../ctg_sql.py, with two differences: no raw JSON is kept (the serving store must fit a 5 GB volume), and the few
fields the app used to read from the JSON are now plain columns: status_verified_date, allocation, masking, arm_types, keywords."""
P = "protocolSection"

FLAT_COLS = ["nct_id", "brief_title", "official_title", "org_name", "org_class", "lead_sponsor", "sponsor_class", "study_type", "phases",
             "overall_status", "why_stopped", "start_date", "primary_completion_date", "completion_date", "first_post_date",
             "last_update_post_date", "results_first_post_date", "enrollment", "enrollment_type", "has_results",
             "status_verified_date", "allocation", "masking", "arm_types", "keywords"]


def flat(src):
    return f"""SELECT nct_id,
  {P}->>'$.identificationModule.briefTitle' AS brief_title, {P}->>'$.identificationModule.officialTitle' AS official_title,
  {P}->>'$.identificationModule.organization.fullName' AS org_name, {P}->>'$.identificationModule.organization.class' AS org_class,
  {P}->>'$.sponsorCollaboratorsModule.leadSponsor.name' AS lead_sponsor, {P}->>'$.sponsorCollaboratorsModule.leadSponsor.class' AS sponsor_class,
  {P}->>'$.designModule.studyType' AS study_type,
  array_to_string(from_json({P}->'$.designModule.phases','["VARCHAR"]'), ',') AS phases,
  {P}->>'$.statusModule.overallStatus' AS overall_status, {P}->>'$.statusModule.whyStopped' AS why_stopped,
  {P}->>'$.statusModule.startDateStruct.date' AS start_date, {P}->>'$.statusModule.primaryCompletionDateStruct.date' AS primary_completion_date,
  {P}->>'$.statusModule.completionDateStruct.date' AS completion_date, {P}->>'$.statusModule.studyFirstPostDateStruct.date' AS first_post_date,
  {P}->>'$.statusModule.lastUpdatePostDateStruct.date' AS last_update_post_date, {P}->>'$.statusModule.resultsFirstPostDateStruct.date' AS results_first_post_date,
  try_cast({P}->>'$.designModule.enrollmentInfo.count' AS INTEGER) AS enrollment, {P}->>'$.designModule.enrollmentInfo.type' AS enrollment_type,
  has_results,
  {P}->>'$.statusModule.statusVerifiedDate' AS status_verified_date,
  {P}->>'$.designModule.designInfo.allocation' AS allocation,
  {P}->>'$.designModule.designInfo.maskingInfo.masking' AS masking,
  array_to_string(list_sort(list_distinct(list_filter(list_transform(coalesce(from_json({P}->'$.armsInterventionsModule.armGroups','["JSON"]'), []::JSON[]), lambda a: a->>'$.type'), lambda t: t IS NOT NULL))), ',') AS arm_types,
  array_to_string(from_json({P}->'$.conditionsModule.keywords','["VARCHAR"]'), '|') AS keywords
FROM {src}"""


def sites(src):
    return f"""SELECT nct_id, l->>'$.facility' AS facility, l->>'$.city' AS city, l->>'$.state' AS state,
       l->>'$.country' AS country, l->>'$.zip' AS zip, l->>'$.status' AS site_status
FROM (SELECT nct_id, unnest(from_json({P}->'$.contactsLocationsModule.locations','["JSON"]')) AS l
      FROM {src} WHERE ({P}->'$.contactsLocationsModule.locations') IS NOT NULL)"""


def conditions(src):
    return f"""SELECT nct_id, 'text' AS kind, NULL AS mesh_id, c AS term
FROM (SELECT nct_id, unnest(from_json({P}->'$.conditionsModule.conditions','["VARCHAR"]')) AS c
      FROM {src} WHERE ({P}->'$.conditionsModule.conditions') IS NOT NULL)
UNION ALL
SELECT nct_id, 'mesh', m->>'$.id', m->>'$.term'
FROM (SELECT nct_id, unnest(from_json(derivedSection->'$.conditionBrowseModule.meshes','["JSON"]')) AS m
      FROM {src} WHERE (derivedSection->'$.conditionBrowseModule.meshes') IS NOT NULL)
UNION ALL
SELECT nct_id, 'ancestor', m->>'$.id', m->>'$.term'
FROM (SELECT nct_id, unnest(from_json(derivedSection->'$.conditionBrowseModule.ancestors','["JSON"]')) AS m
      FROM {src} WHERE (derivedSection->'$.conditionBrowseModule.ancestors') IS NOT NULL)"""


def interventions(src):
    return f"""SELECT nct_id, i->>'$.type' AS type, i->>'$.name' AS name, i->>'$.description' AS description
FROM (SELECT nct_id, unnest(from_json({P}->'$.armsInterventionsModule.interventions','["JSON"]')) AS i
      FROM {src} WHERE ({P}->'$.armsInterventionsModule.interventions') IS NOT NULL)"""


def outcomes(src):
    return f"""SELECT nct_id, 'primary' AS kind, o->>'$.measure' AS measure, o->>'$.timeFrame' AS time_frame, o->>'$.description' AS description
FROM (SELECT nct_id, unnest(from_json({P}->'$.outcomesModule.primaryOutcomes','["JSON"]')) AS o
      FROM {src} WHERE ({P}->'$.outcomesModule.primaryOutcomes') IS NOT NULL)
UNION ALL
SELECT nct_id, 'secondary', o->>'$.measure', o->>'$.timeFrame', o->>'$.description'
FROM (SELECT nct_id, unnest(from_json({P}->'$.outcomesModule.secondaryOutcomes','["JSON"]')) AS o
      FROM {src} WHERE ({P}->'$.outcomesModule.secondaryOutcomes') IS NOT NULL)"""


def eligibility(src):
    return f"""SELECT nct_id, {P}->>'$.eligibilityModule.eligibilityCriteria' AS criteria,
  {P}->>'$.eligibilityModule.minimumAge' AS min_age, {P}->>'$.eligibilityModule.maximumAge' AS max_age,
  {P}->>'$.eligibilityModule.sex' AS sex, {P}->>'$.eligibilityModule.healthyVolunteers' AS healthy_volunteers
FROM {src} WHERE ({P}->'$.eligibilityModule') IS NOT NULL"""


CHILDREN = {"study_sites": sites, "study_conditions": conditions, "study_interventions": interventions,
            "study_outcomes": outcomes, "study_eligibility": eligibility}
