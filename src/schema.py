from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class GeneratorGroup(BaseModel):
    unit_prefix: str = Field(
        description="Letters/prefix used for the generator ID, e.g., 'EG-' or 'GEN-'."
    )
    start_unit_number: int = Field(
        description="Starting unit number in this group (e.g., 1 if 'EG-1 through EG-15', or 4 if single unit 'EG-4')."
    )
    end_unit_number: int = Field(
        description="Ending unit number in this group (e.g., 15 if 'EG-1 through EG-15', or 4 if single unit 'EG-4')."
    )
    raw_unit_id_text: str = Field(
        description="Exact Reference No. text from the Equipment List table, e.g., 'EG-1 through EG-15'."
    )
    equipment_status: Literal["New_or_Modified", "Previously_Permitted_Active", "Removed_or_Retired"] = Field(
        description="Whether listed under Equipment to be Constructed/Modified, Previously Permitted Equipment, or Removed."
    )
    building_or_phase_label: Optional[str] = Field(
        default=None,
        description="Building name, phase, or data hall label if stated in the table (e.g., 'Bldg 1', 'IAD-12')."
    )
    engine_usage_type: Literal["Emergency", "Non-Emergency", "Unknown"] = Field(
        description="Whether permitted as an Emergency diesel engine-generator or Non-Emergency."
    )
    rated_capacity_value: float = Field(
        description="Numeric power rating of a SINGLE generator in this group (e.g., 3000)."
    )
    rated_capacity_unit: Literal["kW", "MW", "bhp"] = Field(
        description="Unit of power rating: kW, MW, or bhp."
    )
    epa_tier_level: Literal["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 4-Equivalent", "Unlisted"] = Field(
        description="EPA emission tier rating stated for this engine."
    )
    has_scr_control: bool = Field(
        description="True if Selective Catalytic Reduction (SCR) or catalyzed DPF is listed as pollution control."
    )
    max_operating_hours_per_unit_yr: Optional[float] = Field(
        default=None,
        description="Max permitted operating hours per year per unit (often 500 hrs/yr for emergency ops)."
    )
    nox_lb_hr_per_unit: Optional[float] = Field(default=None, description="Hourly NOx limit (lb/hr) for a single unit.")
    co_lb_hr_per_unit: Optional[float] = Field(default=None, description="Hourly CO limit (lb/hr) for a single unit.")
    pm25_lb_hr_per_unit: Optional[float] = Field(default=None, description="Hourly PM2.5 limit (lb/hr) for a single unit.")
    voc_lb_hr_per_unit: Optional[float] = Field(default=None, description="Hourly VOC limit (lb/hr) for a single unit.")
    so2_lb_hr_per_unit: Optional[float] = Field(default=None, description="Hourly SO2 limit (lb/hr) for a single unit.")
    
    source_page_numbers: str = Field(
        description="PDF page number(s) where this generator's specs and emission limits were pulled from."
    )
    verbatim_evidence_quote: str = Field(
        description="Short exact text/row snippet from the PDF verifying the capacity and NOx limit."
    )


class DEQPermitExtraction(BaseModel):
    registration_number: str = Field(description="5-digit base Virginia DEQ Registration Number (e.g., '73670').")
    facility_name: str = Field(description="Facility name from the permit cover page.")
    primary_street_address: str = Field(
        description="The FIRST single physical street address of the facility (used for geocoding)."
    )
    additional_campus_addresses: Optional[List[str]] = Field(
        default=None,
        description="Any additional/adjacent street addresses listed on the permit for this campus."
    )
    county_or_city: str = Field(description="Virginia county or city (e.g., Loudoun, Prince William, Fairfax).")
    permit_issue_date: Optional[str] = Field(default=None, description="Permit issuance date in YYYY-MM-DD format.")
    supersedes_prior_permit: bool = Field(
        description="True if the permit states it combines terms from or supersedes an earlier permit document."
    )
    superseded_permit_dates: Optional[str] = Field(
        default=None, description="Date(s) of the superseded prior permit(s), if stated."
    )
    
    fuel_type: str = Field(description="Permitted fuel type, e.g., 'Ultra-Low Sulfur Diesel (ULSD)'.")
    max_fuel_sulfur_ppm: Optional[float] = Field(default=None, description="Max sulfur content in ppm (e.g., 15).")
    combined_annual_fuel_limit_gallons: Optional[float] = Field(
        default=None, description="Facility-wide annual diesel fuel throughput limit in gallons/year."
    )
    
    facility_nox_tpy_limit: Optional[float] = Field(default=None, description="Facility-wide annual NOx cap (tons/yr).")
    facility_co_tpy_limit: Optional[float] = Field(default=None, description="Facility-wide annual CO cap (tons/yr).")
    facility_pm25_tpy_limit: Optional[float] = Field(default=None, description="Facility-wide annual PM2.5 cap (tons/yr).")
    facility_voc_tpy_limit: Optional[float] = Field(default=None, description="Facility-wide annual VOC cap (tons/yr).")
    facility_so2_tpy_limit: Optional[float] = Field(default=None, description="Facility-wide annual SO2 cap (tons/yr).")

    generator_groups: List[GeneratorGroup] = Field(
        description="All generator groups listed in the permit."
    )

    def run_audit_flags(self) -> List[str]:
        flags = []
        if self.facility_nox_tpy_limit and self.facility_nox_tpy_limit > 105.0:
            flags.append(f"HIGH_NOX_TPY ({self.facility_nox_tpy_limit})")
        if self.facility_nox_tpy_limit and self.facility_pm25_tpy_limit:
            if self.facility_pm25_tpy_limit > self.facility_nox_tpy_limit:
                flags.append("RATIO_ERROR: PM2.5 > NOx")
        return flags

    def to_individual_generator_rows(self) -> List[dict]:
        """Unrolls every active generator group into 1 row per individual generator."""
        facility_base = self.model_dump(exclude={"generator_groups"})
        facility_base["additional_campus_addresses"] = "; ".join(self.additional_campus_addresses or [])
        facility_base["audit_flags"] = "; ".join(self.run_audit_flags()) or "PASS"
        
        individual_rows = []
        for group in self.generator_groups:
            if group.equipment_status == "Removed_or_Retired":
                continue  # Never include retired/removed units in active inventory
                
            group_data = group.model_dump(exclude={"unit_prefix", "start_unit_number", "end_unit_number"})
            start = min(group.start_unit_number, group.end_unit_number)
            end = max(group.start_unit_number, group.end_unit_number)
            
            for unit_num in range(start, end + 1):
                row = {
                    **facility_base,
                    "generator_id": f"{group.unit_prefix}{unit_num}",
                    **group_data
                }
                individual_rows.append(row)
        return individual_rows
