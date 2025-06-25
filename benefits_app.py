import streamlit as st
from dataclasses import dataclass
from typing import List, Tuple
import pandas as pd
import plotly.express as px

# ================== CONSTANTS ==================
ANNUAL_GRANT_PER_DAY_THRESHOLD = 32
ANNUAL_GRANT_AMOUNT_THRESHOLD_1 = 1200
ANNUAL_GRANT_AMOUNT_THRESHOLD_2 = 2500
ANNUAL_GRANT_AMOUNT_THRESHOLD_3 = 4000

FAMILY_GRANT_PER_10_DAYS = 1000
PERSONAL_EXPENSES_GRANT_PER_10_DAYS = 466
ROAD_6_MAX_REFUND = 300
BABYSITTER_MAX_COMBATANT = 3500
BABYSITTER_MAX_REAR = 2000
DOG_BOARDING_MAX = 500
THERAPY_MAX_LOW_DAYS = 1500
THERAPY_MAX_HIGH_DAYS = 2500
THERAPY_DAYS_THRESHOLD = 20
TUITION_PERCENT_COMBATANT = 1.0
TUITION_DAYS_THRESHOLD = 20
CAMPS_MAX_COMBATANT_FAMILY = 2000
SPOUSE_ONE_TIME_GRANT = 4500
TZAV_8_DAYS_FOR_TRAINING = 45

# ================== DATA CLASSES ==================
@dataclass
class Entitlement:
    category: str
    name: str
    notes: str
    amount: float | str
    payment_type: str


# ================== CALCULATION ==================
def calculate_benefits(
    avg_salary: float,
    reserve_days: int,
    unit_type: str,
    num_children: int,
    is_married: bool,
    has_non_working_spouse: bool,
    is_student: bool,
    tuition_cost: float,
    used_road_6: bool,
    road_6_cost: float,
    babysitter_cost: float,
    dog_boarding_cost: float,
    vacation_cancel_cost: float,
    therapy_cost: float,
    camps_cost: float,
    is_tzav_8: bool,
    mortgage_rent_cost_input: float,
    needs_dedicated_medical_assistance: bool,
    needs_preferred_loans: bool,
) -> Tuple[List[Entitlement], float, float, float, List[dict]]:
    """Return entitlements, salary compensation and totals."""

    entitlements: List[Entitlement] = []
    total_immediate = 0.0
    total_future = 0.0
    monetary_breakdown: List[dict] = []

    daily_salary_compensation = 0.0
    if avg_salary > 0 and reserve_days > 0:
        daily_salary_compensation = (avg_salary / 30) * reserve_days
        entitlements.append(
            Entitlement(
                "תשלום שכר",
                "תגמול ביטוח לאומי",
                f"תשלום עבור {reserve_days} ימי מילואים לפי ממוצע שכר חודשי.",
                daily_salary_compensation,
                "מיידי",
            )
        )
        total_immediate += daily_salary_compensation

    annual_grant = 0
    if reserve_days >= ANNUAL_GRANT_PER_DAY_THRESHOLD:
        if reserve_days >= 200:
            annual_grant = ANNUAL_GRANT_AMOUNT_THRESHOLD_3
        elif reserve_days >= 60:
            annual_grant = ANNUAL_GRANT_AMOUNT_THRESHOLD_2
        else:
            annual_grant = ANNUAL_GRANT_AMOUNT_THRESHOLD_1

    if annual_grant:
        entitlements.append(
            Entitlement(
                "מענקים שנתיים",
                "מענק שנתי",
                f"מענק משוער עבור {reserve_days} ימי שירות.",
                annual_grant,
                "עתידי (מאי)",
            )
        )
        total_future += annual_grant
        monetary_breakdown.append({"name": "מענק שנתי", "value": annual_grant})

    family_grant = 0
    if is_married and reserve_days > 30 and num_children > 0:
        additional_days = reserve_days - 30
        family_grant = (additional_days // 10) * FAMILY_GRANT_PER_10_DAYS
        if family_grant:
            entitlements.append(
                Entitlement(
                    "מענקים מיוחדים",
                    "מענק משפחה מוגדלת",
                    "תשלום נוסף למשפחות עבור כל 10 ימי שירות מעבר ל‑30.",
                    family_grant,
                    "מיידי",
                )
            )
            total_immediate += family_grant
            monetary_breakdown.append({"name": "מענק משפחה מוגדלת", "value": family_grant})

    personal_expenses_grant = 0
    if reserve_days > 0:
        personal_expenses_grant = (reserve_days // 10) * PERSONAL_EXPENSES_GRANT_PER_10_DAYS
        if personal_expenses_grant:
            entitlements.append(
                Entitlement(
                    "מענקים מיוחדים",
                    "מענק הוצאות אישיות מוגדל",
                    f"{PERSONAL_EXPENSES_GRANT_PER_10_DAYS} ש""ח לכל 10 ימים.",
                    personal_expenses_grant,
                    "מיידי",
                )
            )
            total_immediate += personal_expenses_grant
            monetary_breakdown.append({"name": "מענק הוצאות אישיות מוגדל", "value": personal_expenses_grant})

    if used_road_6 and road_6_cost > 0:
        refund = min(road_6_cost, ROAD_6_MAX_REFUND)
        entitlements.append(
            Entitlement(
                "מענקי הוצאות",
                "החזר כביש 6",
                f"החזר עד {ROAD_6_MAX_REFUND} ש""ח לחודש.",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "החזר כביש 6", "value": refund})

    if num_children > 0 and babysitter_cost > 0:
        max_refund = BABYSITTER_MAX_COMBATANT if unit_type == "לוחם" else BABYSITTER_MAX_REAR
        refund = min(babysitter_cost, max_refund)
        entitlements.append(
            Entitlement(
                "החזרי הוצאות אישיות",
                "בייביסיטר",
                f"החזר עד {max_refund} ש""ח לחודש.",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "בייביסיטר", "value": refund})

    if dog_boarding_cost > 0:
        refund = min(dog_boarding_cost, DOG_BOARDING_MAX)
        entitlements.append(
            Entitlement(
                "החזרי הוצאות אישיות",
                "פנסיון כלבים",
                f"החזר עד {DOG_BOARDING_MAX} ש""ח.",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "פנסיון כלבים", "value": refund})

    if vacation_cancel_cost > 0:
        entitlements.append(
            Entitlement(
                "החזרי הוצאות",
                "ביטול חופשה וטיסה",
                "פיצוי מלא או חלקי בהתאם לתנאים.",
                vacation_cancel_cost,
                "מיידי",
            )
        )
        total_immediate += vacation_cancel_cost
        monetary_breakdown.append({"name": "ביטול חופשה וטיסה", "value": vacation_cancel_cost})

    if therapy_cost > 0:
        limit = THERAPY_MAX_HIGH_DAYS if unit_type == "לוחם" and reserve_days >= THERAPY_DAYS_THRESHOLD else THERAPY_MAX_LOW_DAYS
        refund = min(therapy_cost, limit)
        entitlements.append(
            Entitlement(
                "טיפול רגשי ונפשי",
                "טיפול אישי וזוגי",
                f"החזר עד {limit} ש""ח.",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "טיפול רגשי ונפשי", "value": refund})

    if is_student and tuition_cost > 0 and unit_type == "לוחם" and reserve_days >= TUITION_DAYS_THRESHOLD:
        refund = tuition_cost * TUITION_PERCENT_COMBATANT
        entitlements.append(
            Entitlement(
                "זכאות מיוחדת לסטודנטים",
                "החזר שכר לימוד",
                "עד 100% ללוחמים (תלוי במספר ימי שירות).",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "החזר שכר לימוד", "value": refund})

    if num_children > 0 and camps_cost > 0 and unit_type == "לוחם":
        refund = min(camps_cost, CAMPS_MAX_COMBATANT_FAMILY)
        entitlements.append(
            Entitlement(
                "הטבות משפחתיות",
                "השתתפות בקייטנות",
                f"עד {CAMPS_MAX_COMBATANT_FAMILY} ש""ח בשנה למשפחה.",
                refund,
                "מיידי",
            )
        )
        total_immediate += refund
        monetary_breakdown.append({"name": "השתתפות בקייטנות", "value": refund})

    if has_non_working_spouse and is_married:
        entitlements.append(
            Entitlement(
                "מענקים מיוחדים",
                "מענק חד פעמי לבן זוג לא עובד",
                "חד פעמי.",
                SPOUSE_ONE_TIME_GRANT,
                "מיידי",
            )
        )
        total_immediate += SPOUSE_ONE_TIME_GRANT
        monetary_breakdown.append({"name": "מענק חד פעמי לבן זוג לא עובד", "value": SPOUSE_ONE_TIME_GRANT})

    if is_tzav_8 and reserve_days >= TZAV_8_DAYS_FOR_TRAINING:
        entitlements.append(
            Entitlement(
                "הטבות תעסוקתיות",
                "שוברים להכשרה מקצועית",
                f"למשרתים {TZAV_8_DAYS_FOR_TRAINING} ימים ומעלה בצו 8.",
                "לא כספי",
                "שובר",
            )
        )

    if reserve_days >= 20:
        entitlements.append(
            Entitlement(
                "הטבות נוספות",
                "שוברי חופשה",
                "שוברים לחופשה/נופש.",
                "לא כספי",
                "שובר",
            )
        )

    if mortgage_rent_cost_input > 0:
        entitlements.append(
            Entitlement(
                "הטבות מגורים",
                "סיוע בשכר דירה/משכנתא",
                f"סיוע עד {mortgage_rent_cost_input} ש""ח.",
                mortgage_rent_cost_input,
                "מיידי",
            )
        )
        total_immediate += mortgage_rent_cost_input
        monetary_breakdown.append({"name": "סיוע שכר דירה/משכנתא", "value": mortgage_rent_cost_input})

    if reserve_days >= 10:
        general_benefits = [
            ("הנחות באגרות רישוי"),
            ("הטבות בתחבורה ציבורית"),
            ("הטבות בביטוחי בריאות משלימים"),
            ("הטבות בארנונה / מים (רשות מקומית)"),
            ("הטבות במוסדות תרבות ופנאי"),
            ("הטבות בנופש ואירוח"),
        ]
        for g in general_benefits:
            entitlements.append(
                Entitlement("הטבות כלליות", g, "", "לא כספי", "הטבה")
            )

    if needs_dedicated_medical_assistance:
        entitlements.append(
            Entitlement(
                "בריאות",
                "סיוע רפואי ייעודי",
                "סיוע במידה של פציעה/מחלה הקשורה לשירות.",
                "לא כספי",
                "הטבה",
            )
        )

    if needs_preferred_loans:
        entitlements.append(
            Entitlement(
                "הטבות כלכליות",
                "הלוואות בתנאים מועדפים",
                "דרך בנקים או קרנות מסוימות.",
                "לא כספי",
                "הטבה",
            )
        )

    return entitlements, daily_salary_compensation, total_immediate, total_future, monetary_breakdown


# ================== FOOTER ==================
def add_footer():
    st.markdown("---")
    st.markdown("**@2025 Drishti Consulting | Designed by Dr. Luvchik**")
    st.markdown("All right reserved")


def render_summary(entitlements: List[Entitlement], salary: float, total_immediate: float, total_future: float, chart_data: List[dict], reserve_days: int):
    st.subheader("סיכום הטבות וחישובים")
    daily_salary_value = salary / reserve_days if reserve_days else 0
    total_all = salary + total_immediate + total_future
    daily_with_benefits = total_all / reserve_days if reserve_days else 0

    c1, c2 = st.columns(2)
    c1.metric("שווי יום מילואים (שכר בלבד)", f"{daily_salary_value:,.2f} ש""ח")
    c2.metric("שווי יום מילואים (כל ההטבות)", f"{daily_with_benefits:,.2f} ש""ח")

    chart_items = [x for x in chart_data if x["value"] > 0]
    if chart_items:
        dfc = pd.DataFrame(chart_items)
        fig = px.pie(dfc, values="value", names="name", title="הרכב תוספות")
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    if entitlements:
        df = pd.DataFrame([e.__dict__ for e in entitlements])
        df["amount"] = df["amount"].apply(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else x)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("לא נמצאו הטבות כספיות")


def main():
    st.set_page_config(layout="wide", page_title="מחשבון הטבות")
    st.title("מחשבון הטבות ושווי יום מילואים")
    tab1, tab2 = st.tabs(["Input", "Summary"])

    with tab1:
        st.subheader("נתוני שכר ושירות")
        avg_salary = st.number_input("שכר ממוצע ב‑3 חודשים (נטו)", min_value=0.0, value=10000.0, step=100.0)
        reserve_days = st.number_input("ימי מילואים השנה", min_value=0, value=30, step=1)
        unit_type = st.selectbox("סוג יחידה", ["לוחם", "עורף"])

        st.subheader("פרטים אישיים")
        is_married = st.selectbox("האם נשואים?", ["לא", "כן"]) == "כן"
        num_children = st.number_input("מספר ילדים", min_value=0, value=0, step=1)
        has_non_working_spouse = st.selectbox("האם בן/בת הזוג לא עובד?", ["לא", "כן"]) == "כן"
        is_student = st.selectbox("האם סטודנט?", ["לא", "כן"]) == "כן"
        is_tzav_8 = st.selectbox("האם שירתו בצו 8?", ["לא", "כן"]) == "כן"

        st.subheader("הוצאות")
        used_road_6 = st.selectbox("השתמשו בכביש 6?", ["לא", "כן"]) == "כן"
        road_6_cost = st.number_input("עלות כביש 6", min_value=0.0, value=0.0, step=10.0) if used_road_6 else 0
        babysitter_cost = st.number_input("עלות בייביסיטר", min_value=0.0, value=0.0, step=50.0)
        dog_boarding_cost = st.number_input("עלות פנסיון כלבים", min_value=0.0, value=0.0, step=50.0)
        vacation_cancel_cost = st.number_input("עלות ביטול חופשה", min_value=0.0, value=0.0, step=100.0)
        therapy_cost = st.number_input("עלות טיפול רגשי", min_value=0.0, value=0.0, step=50.0)
        camps_cost = st.number_input("עלות קייטנות", min_value=0.0, value=0.0, step=50.0)
        tuition_cost = st.number_input("שכר לימוד (לסטודנטים)", min_value=0.0, value=0.0, step=100.0)
        mortgage_help = st.number_input("סיוע בשכר דירה/משכנתא", min_value=0.0, value=0.0, step=50.0)
        needs_med = st.selectbox("צריכים סיוע רפואי ייעודי?", ["לא", "כן"]) == "כן"
        needs_loans = st.selectbox("מעוניינים בהלוואות בתנאים מועדפים?", ["לא", "כן"]) == "כן"

        if st.button("חשב"):
            result = calculate_benefits(
                avg_salary,
                reserve_days,
                unit_type,
                num_children,
                is_married,
                has_non_working_spouse,
                is_student,
                tuition_cost,
                used_road_6,
                road_6_cost,
                babysitter_cost,
                dog_boarding_cost,
                vacation_cancel_cost,
                therapy_cost,
                camps_cost,
                is_tzav_8,
                mortgage_help,
                needs_med,
                needs_loans,
            )
            st.session_state["res"] = result
            st.session_state["rd"] = reserve_days
            st.switch_page("benefits_app.py#Summary")

        add_footer()

    with tab2:
        if "res" in st.session_state:
            ent, salary, imm, fut, chart = st.session_state["res"]
            render_summary(ent, salary, imm, fut, chart, st.session_state.get("rd", 0))
        else:
            st.info("הזן נתונים בטאב הקודם ולחץ חישוב")
        add_footer()


if __name__ == "__main__":
    main()
