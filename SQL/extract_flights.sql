-- Actual departure counts at 15-minute grain for the lounges' airports.
WITH outlet_airports AS (
    SELECT DISTINCT UPPER(TRIM(LOCATION_CODE_TEXT)) AS airport_code
    FROM STAGING_QUALITY.SF_PARTNERSHIP.SQ_SF_PARTNERSHIP__ACCOUNT
    WHERE ACCOUNT_STATUS = 'Active'
      AND LOCATION_TYPE = 'Airport'
      AND UPPER(TRIM(CODE)) IN ({{ outlet_codes }})
      AND LOCATION_CODE_TEXT IS NOT NULL
)
SELECT
    f.VISIT_DATE AS flight_interval,
    UPPER(TRIM(f.AIRPORT_CODE)) AS airport_code,
    SUM(f.DEP_FLIGHT_COUNT) AS departure_flight_count
FROM SUBDM_COLLINSON_INVENTORY.DATAMART.AGG__ACTUALS_15MIN f
WHERE f.VISIT_DATE >= {{ start_datetime }}::TIMESTAMP
  AND f.VISIT_DATE < {{ end_datetime }}::TIMESTAMP
  AND UPPER(TRIM(f.AIRPORT_CODE)) IN (
      SELECT airport_code FROM outlet_airports
  )
GROUP BY f.VISIT_DATE, UPPER(TRIM(f.AIRPORT_CODE))
ORDER BY airport_code, flight_interval;
