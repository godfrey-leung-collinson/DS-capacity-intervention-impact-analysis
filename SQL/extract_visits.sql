-- PP/LK arrivals at 15-minute grain for configured intervention lounges.
WITH outlet_ref AS (
    SELECT
        UPPER(TRIM(CODE)) AS outlet_code,
        UPPER(TRIM(LOCATION_CODE_TEXT)) AS airport_code,
        NAME AS outlet_name,
        NUMBER_OF_SEATS AS number_of_seats
    FROM STAGING_QUALITY.SF_PARTNERSHIP.SQ_SF_PARTNERSHIP__ACCOUNT
    WHERE ACCOUNT_STATUS = 'Active'
      AND LOCATION_TYPE = 'Airport'
      AND CODE NOT LIKE 'TEST%'
      AND NUMBER_OF_SEATS > 0
      AND NUMBER_OF_SEATS < 5000
      AND UPPER(TRIM(CODE)) IN ({{ outlet_codes }})
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY UPPER(TRIM(CODE))
        ORDER BY LAST_MODIFIED_DATE DESC
    ) = 1
)
SELECT
    v.VISIT_INTERVAL AS visit_interval,
    r.outlet_code,
    r.airport_code,
    r.outlet_name,
    r.number_of_seats,
    SUM(v.TOTAL_VISITS) AS total_visits
FROM ANALYTICS.DATAMART.AGG__VISITS_AGG_15MIN v
INNER JOIN outlet_ref r
    ON UPPER(TRIM(v.OUTLET_CODE)) = r.outlet_code
WHERE v.VISIT_INTERVAL >= {{ start_datetime }}::TIMESTAMP
  AND v.VISIT_INTERVAL < {{ end_datetime }}::TIMESTAMP
GROUP BY ALL
ORDER BY outlet_code, visit_interval;
