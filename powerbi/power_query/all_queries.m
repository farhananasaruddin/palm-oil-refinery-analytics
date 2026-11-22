// =============================================================================
//  POWER QUERY (M)  -  paste each block into Power BI Desktop:
//  Home > Transform data > New Source > Blank Query > Advanced Editor
//  Rename each query to the name in its header comment.
//
//  1) Create the parameter first:  Home > Manage Parameters > New
//       Name: DataFolder   Type: Text
//       Current value: C:\path\to\palm-oil-refinery-analytics\data\processed\
//     (keep the trailing backslash)
// =============================================================================


// ---------- Query name: fact_batch --------------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "fact_batch.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"batch_id", type text}, {"production_date", type date}, {"shift", type text},
        {"line_code", type text}, {"supplier_id", type text}, {"operator_id", type text},
        {"cpo_input_mt", type number}, {"cpo_ffa_pct", type number}, {"cpo_dobi", type number},
        {"cpo_moisture_pct", type number}, {"bleaching_earth_pct", type number},
        {"phosphoric_acid_pct", type number}, {"deo_temp_c", type number},
        {"deo_vacuum_mbar", type number}, {"rbdpo_output_mt", type number},
        {"pfad_output_mt", type number}, {"refining_yield_pct", type number},
        {"pfad_yield_pct", type number}, {"refining_loss_pct", type number},
        {"rbdpo_ffa_pct", type number}, {"color_red", type number},
        {"rbdpo_moisture_pct", type number}, {"peroxide_value", type number},
        {"has_lab_result", Int64.Type}, {"is_off_spec", Int64.Type}, {"off_spec_reason", type text},
        {"steam_mt", type number}, {"electricity_kwh", type number},
        {"steam_per_mt_cpo", type number}, {"kwh_per_mt_cpo", type number}, {"dq_flags", type text}
    }, "en-US"),
    // Analysis bands used by slicers / axis
    AddFFABand = Table.AddColumn(Typed, "CPO FFA Band", each
        if [cpo_ffa_pct] = null then null
        else if [cpo_ffa_pct] < 3.0 then "1) < 3.0 %"
        else if [cpo_ffa_pct] < 3.5 then "2) 3.0-3.5 %"
        else if [cpo_ffa_pct] < 4.0 then "3) 3.5-4.0 %"
        else if [cpo_ffa_pct] < 4.5 then "4) 4.0-4.5 %"
        else if [cpo_ffa_pct] < 5.0 then "5) 4.5-5.0 %"
        else "6) >= 5.0 %", type text),
    AddDOBIBand = Table.AddColumn(AddFFABand, "DOBI Band", each
        if [cpo_dobi] = null then "Unknown"
        else if [cpo_dobi] < 2.0 then "1) Poor (< 2.0)"
        else if [cpo_dobi] < 2.3 then "2) Fair (2.0-2.3)"
        else if [cpo_dobi] < 2.6 then "3) Good (2.3-2.6)"
        else "4) Excellent (>= 2.6)", type text),
    AddTempBand = Table.AddColumn(AddDOBIBand, "Deo Temp Band", each
        if [deo_temp_c] = null then null
        else Text.From(Number.RoundDown([deo_temp_c] / 2) * 2) & "-" &
             Text.From(Number.RoundDown([deo_temp_c] / 2) * 2 + 2) & " C", type text),
    AddQuality = Table.AddColumn(AddTempBand, "Quality Status", each
        if [has_lab_result] = 0 then "Not tested"
        else if [is_off_spec] = 1 then "Off-spec" else "In spec", type text),
    AddShiftOrder = Table.AddColumn(AddQuality, "Shift Order", each
        if [shift] = "Morning" then 1 else if [shift] = "Evening" then 2 else 3, Int64.Type)
in
    AddShiftOrder


// ---------- Query name: fact_downtime -----------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "fact_downtime.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"event_id", type text}, {"line_code", type text}, {"area", type text},
        {"event_date", type date}, {"shift", type text}, {"start_time", type datetime},
        {"end_time", type datetime}, {"duration_min", type number}, {"category", type text},
        {"description", type text}, {"is_planned", Int64.Type}, {"dq_flags", type text}
    }, "en-US"),
    AddHours = Table.AddColumn(Typed, "duration_h", each [duration_min] / 60, type number),
    AddType  = Table.AddColumn(AddHours, "Stop Type", each if [is_planned] = 1 then "Planned" else "Unplanned", type text)
in
    AddType


// ---------- Query name: dim_date ----------------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "dim_date.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"date_key", type date}, {"year", Int64.Type}, {"quarter", type text},
        {"month_no", Int64.Type}, {"month_name", type text}, {"year_month", type text},
        {"week_of_year", Int64.Type}, {"day_name", type text}, {"is_weekend", Int64.Type},
        {"crop_season", type text}
    }, "en-US"),
    AddMonthStart = Table.AddColumn(Typed, "month_start", each Date.StartOfMonth([date_key]), type date)
in
    AddMonthStart


// ---------- Query name: dim_line ----------------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "dim_line.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"line_code", type text}, {"line_name", type text},
        {"design_capacity_tpd", type number}, {"commissioned_year", Int64.Type}
    }, "en-US")
in
    Typed


// ---------- Query name: dim_supplier ------------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "dim_supplier.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"supplier_id", type text}, {"supplier_name", type text}, {"state", type text},
        {"region", type text}, {"certification", type text}, {"distance_km", type number},
        {"contract_start", type date}
    }, "en-US")
in
    Typed


// ---------- Query name: fact_market_price -------------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "fact_market_price.csv"),
                 [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
        {"year_month", type text}, {"cpo_price_myr_mt", type number},
        {"rbdpo_price_myr_mt", type number}, {"pfad_price_myr_mt", type number}
    }, "en-US"),
    AddSpread = Table.AddColumn(Typed, "rbdpo_cpo_spread_myr", each [rbdpo_price_myr_mt] - [cpo_price_myr_mt], type number)
in
    AddSpread
