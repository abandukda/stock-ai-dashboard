
'''Atlas V60.3 App Patch.'''

from pathlib import Path

p = Path('app.py')
text = p.read_text()
backup = Path('app.py.v60_3_mobile_scoring_backup')
if not backup.exists():
    backup.write_text(text)

changed = False

imports = '''
from services.scoring_calibration import calibrate_top_ai_dataframe
from ui.mobile_cards import render_mobile_top_ai_cards
'''

if 'from services.scoring_calibration import calibrate_top_ai_dataframe' not in text:
    marker = 'import streamlit as st'
    if marker in text:
        text = text.replace(marker, marker + imports, 1)
    else:
        text = imports + '\n' + text
    changed = True

helper = '''
# ==============================
# Atlas V60.3 Top AI Experience
# ==============================
def render_v60_3_top_ai_experience(source_df, title="Top AI Ideas", max_rows=10, show_filters=False):
    # Calibrated scoring + optional mobile cards + existing ranked table.
    try:
        calibrated_df = calibrate_top_ai_dataframe(source_df)
    except Exception:
        calibrated_df = source_df

    try:
        mobile_view = st.toggle("📱 Mobile card view", value=False, key=f"mobile_cards_{title}")
    except Exception:
        mobile_view = False

    if mobile_view:
        try:
            render_mobile_top_ai_cards(calibrated_df, max_rows=max_rows)
            return calibrated_df
        except Exception:
            pass

    return render_v56_ranked_table(
        calibrated_df,
        title=title,
        max_rows=max_rows,
        show_filters=show_filters,
    )
'''

if 'def render_v60_3_top_ai_experience(' not in text:
    text += '\n\n' + helper + '\n'
    changed = True

replacements = {
    'render_v56_ranked_table(source_df, title="Top AI Ideas", max_rows=10, show_filters=False)':
    'render_v60_3_top_ai_experience(source_df, title="Top AI Ideas", max_rows=10, show_filters=False)',

    'render_v56_ranked_table(source_df,title="Top AI Ideas",max_rows=10,show_filters=False)':
    'render_v60_3_top_ai_experience(source_df, title="Top AI Ideas", max_rows=10, show_filters=False)',

    'render_v56_ranked_table(top_df if not top_df.empty else full_df.head(25), title="Top AI Ideas", max_rows=10, show_filters=False)':
    'render_v60_3_top_ai_experience(top_df if not top_df.empty else full_df.head(25), title="Top AI Ideas", max_rows=10, show_filters=False)',
}

for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)
        changed = True

if changed:
    p.write_text(text)
    print('Applied Atlas V60.3 mobile/scoring patch to app.py')
else:
    print('No app.py changes made. Patch may already be applied or exact table call was not found.')
