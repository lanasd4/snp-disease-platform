"""
Admin Components
"""

from pathlib import Path
import html
import re
from datetime import datetime
import sqlite3
import pandas as pd
import streamlit as st

from app.ui.components import notice, page_header, section_title, stat_card
from core.i18n import tr
from core.paths import DATABASE_PATH, PROJECT_ROOT, get_project_root
from core.admin.common import get_registry_path
from core.admin.data_ingestion import run_uploaded_source_pipeline


def sanitize_uploaded_filename(raw_name: str) -> str:
    """Reduce a browser-supplied upload filename to a safe basename."""
    name = str(raw_name or "").replace("\\", "/")
    name = name.rsplit("/", 1)[-1].strip()
    name = name.lstrip(".") or "upload"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "upload"


from app.ui.components import get_database_counts as get_live_counts
from app.views.admin_community import render_community_admin_tab
from core.auth import (
    create_user_account,
    list_users,
    update_user_role,
    set_user_active,
    reset_user_password,
    get_admin_action_logs,
    get_current_user,
)


from core.admin.approval_merge import (
    list_sources_for_review,
    approve_source,
    reject_source,
    load_validation_report_for_source,
    load_rejected_rows_for_source,
    load_processed_rows_for_source,
    export_review_snapshot,
)


from core.admin.gwas_connector import (
    run_gwas_online_update,
    DEFAULT_GWAS_ASSOCIATIONS_URL,
)


from core.admin.final_merge import (
    list_approved_sources,
    list_merged_sources,
    validate_staging_file,
    final_merge_source,
    rollback_source,
    export_merge_snapshot,
)


from core.glossary import (
    load_glossary,
    search_glossary,
    export_glossary_summary,
)

from core.ai.model_manager import (
    get_ollama_status,
    list_installed_models,
    get_active_model,
    set_active_model,
    test_model,
    install_model,
    validate_model_name,
    read_config,
)

try:
    from core.ai.agent import select_best_ollama_model
except Exception:
    select_best_ollama_model = None


ADMIN_VERSION = "admin_v1"


def load_registry() -> pd.DataFrame:
    path = get_registry_path()

    if not path.exists():
        return pd.DataFrame(columns=[
            "source_id",
            "source_name",
            "category",
            "status",
            "enabled",
            "last_update",
            "reliability",
            "raw_path",
            "processed_path",
            "notes"
        ])

    return pd.read_csv(path, dtype=str).fillna("")


def save_registry(df: pd.DataFrame) -> None:
    path = get_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def get_ranked_path() -> Path:
    return get_project_root() / "data" / "processed" / "ranked_associations_initial.csv"


def load_ranked_data() -> pd.DataFrame:
    path = get_ranked_path()

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path, dtype=str)


def get_database_counts() -> pd.DataFrame:
    """Get counts from SQLite if available, otherwise use ranked CSV as fallback."""
    project_root = get_project_root()
    db_path = DATABASE_PATH if DATABASE_PATH.exists() else None

    rows = []

    if db_path is not None:
        try:
            conn = sqlite3.connect(db_path)
            tables_df = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;",
                conn
            )

            for table_name in tables_df["name"].tolist():
                try:
                    count_df = pd.read_sql_query(f"SELECT COUNT(*) AS count FROM {table_name};", conn)
                    rows.append({
                        "object": table_name,
                        "type": "SQLite table",
                        "count": int(count_df["count"].iloc[0]),
                        "source": str(db_path.relative_to(project_root))
                    })
                except Exception:
                    pass

            conn.close()
        except Exception as exc:
            rows.append({
                "object": "SQLite error",
                "type": "error",
                "count": 0,
                "source": str(exc)
            })

    ranked_df = load_ranked_data()

    if not ranked_df.empty:
        fallback_items = [
            ("Ranked associations", len(ranked_df)),
            ("Unique diseases", ranked_df["disease_name"].nunique() if "disease_name" in ranked_df.columns else 0),
            ("Unique SNPs", ranked_df["rsid"].nunique() if "rsid" in ranked_df.columns else 0),
            ("Unique genes", ranked_df["gene_symbol"].nunique() if "gene_symbol" in ranked_df.columns else 0),
        ]

        for object_name, count in fallback_items:
            rows.append({
                "object": object_name,
                "type": "Processed CSV",
                "count": int(count),
                "source": "data/processed/ranked_associations_initial.csv"
            })

    return pd.DataFrame(rows)


def scan_project_files() -> pd.DataFrame:
    """Scan important project files for admin overview."""
    project_root = get_project_root()

    folders = [
        project_root / "data" / "raw",
        project_root / "data" / "processed",
        project_root / "database",
        project_root / "outputs" / "tables",
        project_root / "docs",
    ]

    rows = []

    for folder in folders:
        if not folder.exists():
            continue

        for path in folder.rglob("*"):
            if path.is_file():
                try:
                    size_kb = round(path.stat().st_size / 1024, 2)
                    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    rows.append({
                        "file": str(path.relative_to(project_root)),
                        "folder": str(folder.relative_to(project_root)),
                        "size_kb": size_kb,
                        "modified": modified
                    })
                except Exception:
                    pass

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df.sort_values("modified", ascending=False).head(80)


def run_validation_checks() -> pd.DataFrame:
    """Run data quality checks on ranked_associations_initial.csv and registry."""
    project_root = get_project_root()
    ranked_path = get_ranked_path()
    registry_path = get_registry_path()

    rows = []

    def add_check(name, status, details):
        rows.append({
            "check": name,
            "status": status,
            "details": details,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    if ranked_path.exists():
        add_check("Ranked associations file exists", "passed", str(ranked_path.relative_to(project_root)))
    else:
        add_check("Ranked associations file exists", "failed", "data/processed/ranked_associations_initial.csv not found")
        return pd.DataFrame(rows)

    df = load_ranked_data()

    if df.empty:
        add_check("Ranked associations not empty", "failed", "File is empty or unreadable")
        return pd.DataFrame(rows)
    else:
        add_check("Ranked associations not empty", "passed", f"{len(df)} rows")

    required_cols = ["rsid", "gene_symbol", "disease_name", "p_value", "evidence_tier"]
    missing_cols = [c for c in required_cols if c not in df.columns]

    if missing_cols:
        add_check("Required columns", "warning", "Missing columns: " + ", ".join(missing_cols))
    else:
        add_check("Required columns", "passed", "All required columns are available")

    if "rsid" in df.columns:
        missing_rsid = df["rsid"].isna().sum() + (df["rsid"].astype(str).str.strip() == "").sum()
        status = "passed" if missing_rsid == 0 else "warning"
        add_check("Missing rsID values", status, f"{int(missing_rsid)} missing/blank rsID values")

    if "p_value" in df.columns:
        p_numeric = pd.to_numeric(df["p_value"], errors="coerce")
        invalid_p = int(p_numeric.isna().sum())
        status = "passed" if invalid_p == 0 else "warning"
        add_check("p-value numeric validation", status, f"{invalid_p} invalid p-value entries")

    if "evidence_tier" in df.columns:
        tiers = pd.to_numeric(df["evidence_tier"], errors="coerce")
        invalid_tier = int((~tiers.isin([0, 1, 2, 3])).sum())
        status = "passed" if invalid_tier == 0 else "warning"
        add_check("Evidence level validation", status, f"{invalid_tier} invalid evidence levels")

    duplicate_cols = [c for c in ["disease_name", "rsid", "gene_symbol"] if c in df.columns]

    if duplicate_cols:
        duplicated_count = int(df.duplicated(subset=duplicate_cols).sum())
        status = "passed" if duplicated_count == 0 else "warning"
        add_check("Duplicate key check", status, f"{duplicated_count} duplicated disease-rsid-gene rows")

    arab_cols = [c for c in ["is_arab_related_rule", "is_arab_related_flag", "is_arab_related", "arab_tag"] if c in df.columns]
    if arab_cols:
        add_check("Arab-related classification column", "passed", f"Found: {arab_cols[0]}")
    else:
        add_check("Arab-related classification column", "warning", "No Arab-related column found in ranked file")

    if registry_path.exists():
        registry_df = load_registry()
        add_check("Data source registry", "passed", f"{len(registry_df)} registered sources")
    else:
        add_check("Data source registry", "failed", "Registry file not found")

    return pd.DataFrame(rows)


def _object_count(counts_df: pd.DataFrame, table: str) -> int:
    match = counts_df[counts_df["object"].astype(str) == table] if not counts_df.empty else counts_df
    return int(match["count"].iloc[0]) if not match.empty else 0


def render_overview_tab():
    live = get_live_counts()
    counts_df = pd.DataFrame([{"object": k, "count": v} for k, v in live.items()])
    users_df = list_users()
    registry_df = load_registry()

    section_title(tr("البيانات العلمية", "Scientific data"))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card(tr("الأمراض", "Diseases"), _object_count(counts_df, "Disease"), icon="🩺")
    with c2:
        stat_card(tr("المتغيرات الجينية", "Variants"), f"{_object_count(counts_df, 'SNP'):,}", icon="🧬")
    with c3:
        stat_card(tr("الجينات", "Genes"), f"{_object_count(counts_df, 'Gene'):,}", icon="🧪")
    with c4:
        stat_card(tr("الارتباطات", "Associations"), f"{_object_count(counts_df, 'Association'):,}", icon="🔗")

    section_title(tr("الحسابات ومصادر البيانات", "Accounts and data sources"))
    active = users_df[users_df["is_active"].astype(int) == 1] if not users_df.empty else users_df
    admins = int((active["role"] == "admin").sum()) if not active.empty else 0
    pending = int(registry_df["status"].astype(str).isin(["processed", "pending_approval"]).sum()) \
        if not registry_df.empty and "status" in registry_df.columns else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card(tr("الحسابات الفعّالة", "Active accounts"), len(active), icon="👥")
    with c2:
        stat_card(tr("حسابات الأدمن", "Admins"), admins, icon="🛡️")
    with c3:
        stat_card(tr("مصادر البيانات", "Data sources"), len(registry_df), icon="🗂️")
    with c4:
        stat_card(tr("بانتظار المراجعة", "Awaiting review"), pending, icon="⏳")

    ranked_path = get_ranked_path()
    if ranked_path.exists():
        updated = datetime.fromtimestamp(ranked_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        notice(tr(f"آخر تحديث لملف النتائج المرتبة: {updated}", f"Ranked results last updated: {updated}"))

    with st.expander(tr("تفاصيل أعداد الجداول", "Table counts"), icon="📋"):
        st.dataframe(counts_df, width="stretch", hide_index=True)


def render_sources_tab():
    section_title(tr("إدارة مصادر البيانات", "Data Source Management"))

    registry_df = load_registry()

    if registry_df.empty:
        st.warning(tr("لا يوجد سجل مصادر بيانات.", "No data source registry found."))
    else:
        st.info(tr("يمكن تعديل حالة المصدر أو ملاحظاته ثم الضغط على Save Registry.", "Edit a source's status or notes, then save the registry."))

        edited_df = st.data_editor(
            registry_df,
            width="stretch",
            num_rows="dynamic",
            key=f"{ADMIN_VERSION}_registry_editor"
        )

        if st.button(tr("حفظ سجل المصادر", "Save Registry"), key=f"{ADMIN_VERSION}_save_registry"):
            save_registry(edited_df)
            st.success(tr("تم حفظ سجل مصادر البيانات بنجاح.", "Data source registry saved."))

    st.divider()

    section_title(tr("تسجيل ملف خام جديد", "Register Uploaded Raw File"))

    uploaded_file = st.file_uploader(
        tr("رفع ملف بيانات خام", "Upload raw data file"),
        type=["csv", "tsv", "txt", "xlsx"],
        help=tr("أعمدة مطلوبة: rsid، المرض، الجين، قيمة p", "Required columns: rsid, disease, gene, p-value"),
        key=f"{ADMIN_VERSION}_raw_upload"
    )

    source_name = st.text_input(
        tr("اسم المصدر", "Source name"),
        value="New Uploaded Source",
        key=f"{ADMIN_VERSION}_new_source_name"
    )

    if uploaded_file is not None:
        if st.button(tr("رفع ومعالجة الملف", "Upload and process"), key=f"{ADMIN_VERSION}_register_upload"):
            project_root = get_project_root()
            upload_dir = project_root / "data" / "raw" / "admin_uploaded"
            upload_dir.mkdir(parents=True, exist_ok=True)

            safe_name = sanitize_uploaded_filename(uploaded_file.name)
            target_path = upload_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"

            target_path.write_bytes(uploaded_file.getvalue())

            try:
                with st.spinner(tr("نتحقق من الملف ونعالجه…", "Validating and processing the file…")):
                    result = run_uploaded_source_pipeline(
                        target_path,
                        uploaded_by=(get_current_user() or {}).get("username", "admin"),
                        source_name=source_name,
                    )
            except Exception as exc:
                st.error(f"{tr('تعذرت معالجة الملف: ', 'Could not process the file: ')}{exc}")
                return

            if result["status"] != "processed":
                missing = ", ".join(result["report"].get("missing_required_columns", []))
                st.error(f"{tr('الملف ينقصه أعمدة أساسية: ', 'The file is missing required columns: ')}{missing}")
                return

            st.success(tr(
                f"تمت المعالجة: {result['accepted_rows']} صف مقبول و {result['rejected_rows']} صف مرفوض. "
                "المصدر الآن في «الموافقات» بانتظار المراجعة.",
                f"Processed: {result['accepted_rows']} rows accepted, {result['rejected_rows']} rejected. "
                "The source is now waiting in Approvals.",
            ))


def render_validation_tab():
    section_title(tr("فحوصات جودة البيانات", "Validation Checks"))

    validation_df = run_validation_checks()

    if validation_df.empty:
        st.warning(tr("لا توجد نتائج تحقق.", "No validation results."))
        return

    st.dataframe(validation_df, width="stretch", hide_index=True)

    # Offered as a download only: rendering a page must not write to disk
    # (it ran on every rerun and fails on read-only hosting).
    csv_data = validation_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    st.download_button(
        tr("تحميل تقرير التحقق", "Download Validation Report"),
        data=csv_data,
        file_name="admin_validation_checks.csv",
        mime="text/csv",
        width="stretch",
        key=f"{ADMIN_VERSION}_download_validation"
    )


def render_files_tab():
    section_title(tr("نظرة على الملفات", "Files Overview"))

    files_df = scan_project_files()

    if files_df.empty:
        st.warning(tr("لا توجد ملفات للعرض.", "No files to show."))
        return

    st.dataframe(files_df, width="stretch", hide_index=True)

    section_title(tr("مسار البيانات", "Data Lineage"))

    lineage_df = pd.DataFrame([
        {"step": "1", "stage": "Raw Data", "description": "Original downloaded or uploaded files", "path": "data/raw"},
        {"step": "2", "stage": "Processed Data", "description": "Cleaned and normalized files", "path": "data/processed"},
        {"step": "3", "stage": "SQLite / Ranked CSV", "description": "Loaded searchable structures and ranked association file", "path": "database + data/processed/ranked_associations_initial.csv"},
        {"step": "4", "stage": "Search UI", "description": "Streamlit interface reads ranked data for search and export", "path": "app/views/search.py"},
        {"step": "5", "stage": "Admin Dashboard", "description": "Admin monitors sources, files, validation, and data status", "path": "app/views/admin.py"},
    ])

    st.dataframe(lineage_df, width="stretch", hide_index=True)


def render_run_controls_tab():
    section_title(tr("أدوات تشغيل ومتابعة المعالجة", "Pipeline Controls"))

    if st.button(tr("تشغيل فحص البيانات", "Run Validation Checks"), key=f"{ADMIN_VERSION}_run_validation_button"):
        validation_df = run_validation_checks()
        st.success(tr("تم تشغيل فحوصات التحقق.", "Validation checks ran."))
        st.dataframe(validation_df, width="stretch", hide_index=True)

    ranked_path = get_ranked_path()

    if ranked_path.exists():
        modified = datetime.fromtimestamp(ranked_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        st.write(tr("**ملف النتائج المرتبة:**", "**Ranked file:**"), str(ranked_path.relative_to(get_project_root())))
        st.write(tr("**آخر تعديل:**", "**Last modified:**"), modified)
    else:
        st.warning(tr("ملف ranked_associations_initial.csv غير موجود.", "ranked_associations_initial.csv not found."))


def render_users_tab():
    """User/Admin Management inside Admin Dashboard."""
    section_title(tr("إدارة المستخدمين والأدمن", "User & Admin Management"))

    current_user = get_current_user() or {}
    actor_username = current_user.get("username", "admin")

    st.info(
        tr("هذه اللوحة متاحة فقط بعد تسجيل الدخول بحساب مسؤول النظام. يمكن استخدامها لإضافة حسابات المسؤولين والمستخدمين، وتحديث الأدوار والصلاحيات، وتعطيل الحسابات، وإعادة تعيين كلمات المرور.", "Available to administrators only. Add admin and user accounts, change roles, disable accounts and reset passwords.")
    )

    tab_add_user, tab_manage_users, tab_audit_logs = st.tabs([
        tr("إضافة مستخدم", "Add User"),
        tr("إدارة الحسابات", "Manage Users"),
        tr("سجل العمليات", "Audit Log")
    ])

    with tab_add_user:
        st.markdown("##### " + tr("إضافة حساب جديد", "Add New Account"))

        with st.form("add_user_form"):
            new_username = st.text_input(
                tr("اسم المستخدم", "Username"),
                key="new_username"
            )

            new_role = st.selectbox(
                tr("الصلاحية", "Role"),
                ["user", "admin", "guest"],
                index=0,
                key="new_role"
            )

            new_password = st.text_input(
                tr("كلمة المرور المؤقتة", "Temporary Password"),
                type="password",
                key="new_password"
            )

            confirm_password = st.text_input(
                tr("تأكيد كلمة المرور", "Confirm Password"),
                type="password",
                key="confirm_password"
            )

            new_is_active = st.checkbox(
                tr("حساب مفعّل", "Active account"),
                value=True,
                key="new_is_active"
            )

            submit_new_user = st.form_submit_button(
                tr("إنشاء الحساب", "Create Account"),
                width="stretch"
            )

        if submit_new_user:
            if not new_username.strip():
                st.error(tr("اسم المستخدم مطلوب.", "Username is required."))
            elif len(new_password) < 8:
                st.error(tr("كلمة المرور يجب أن تكون 8 أحرف على الأقل.", "Password must be at least 8 characters."))
            elif new_password != confirm_password:
                st.error(tr("كلمتا المرور غير متطابقتين.", "Passwords do not match."))
            else:
                try:
                    create_user_account(
                        username=new_username,
                        password=new_password,
                        role=new_role,
                        is_active=1 if new_is_active else 0,
                        actor_username=actor_username
                    )
                    st.success(f"{tr('تم إنشاء الحساب بنجاح: ', 'Account created: ')}{new_username} ({new_role})")
                    st.rerun()
                except Exception as exc:
                    st.error(f"{tr('لم يتم إنشاء الحساب: ', 'Account not created: ')}{exc}")

    with tab_manage_users:
        st.markdown("##### " + tr("الحسابات الحالية", "Existing Accounts"))

        users_df = list_users()

        if users_df.empty:
            st.warning(tr("لا توجد حسابات مستخدمين.", "No user accounts."))
        else:
            st.dataframe(users_df, width="stretch", hide_index=True)

            st.divider()
            st.markdown("##### " + tr("تعديل حساب محدد", "Update Selected Account"))

            options = {}
            for _, row in users_df.iterrows():
                status_text = "active" if int(row["is_active"]) == 1 else "disabled"
                label = f"{row['username']} | {row['role']} | {status_text} | ID={row['user_id']}"
                options[label] = int(row["user_id"])

            selected_label = st.selectbox(
                tr("اختر الحساب", "Select account"),
                list(options.keys()),
                key="selected_user"
            )

            selected_user_id = options[selected_label]
            selected_row = users_df[users_df["user_id"] == selected_user_id].iloc[0].to_dict()

            st.caption(
                f"{tr('المحدد: ', 'Selected: ')}{selected_row['username']} | "
                f"{tr('الصلاحية الحالية', 'Current role')}: {selected_row['role']} | "
                f"{tr('مفعّل', 'Active')}: {selected_row['is_active']}"
            )

            role_options = ["admin", "user", "guest"]
            current_role = str(selected_row.get("role", "user"))
            current_role_index = role_options.index(current_role) if current_role in role_options else 1

            c1, c2 = st.columns(2)

            with c1:
                selected_new_role = st.selectbox(
                    tr("الصلاحية الجديدة", "New role"),
                    role_options,
                    index=current_role_index,
                    key="update_role_select"
                )

                if st.button(
                    tr("تحديث الصلاحية", "Update Role"),
                    width="stretch",
                    key="update_role_button"
                ):
                    try:
                        update_user_role(
                            user_id=selected_user_id,
                            new_role=selected_new_role,
                            actor_username=actor_username
                        )
                        st.success(tr("تم تحديث الصلاحية.", "Role updated."))
                        st.rerun()
                    except Exception as exc:
                        st.error(f"{tr('تعذر تحديث الصلاحية: ', 'Could not update the role: ')}{exc}")

            with c2:
                current_active = int(selected_row.get("is_active", 1))
                status_options = ["Active", "Disabled"]
                status_index = 0 if current_active == 1 else 1

                selected_status = st.selectbox(
                    tr("حالة الحساب", "Account status"),
                    status_options,
                    index=status_index,
                    key="update_status_select"
                )

                if st.button(
                    tr("تحديث الحالة", "Update Status"),
                    width="stretch",
                    key="update_status_button"
                ):
                    try:
                        set_user_active(
                            user_id=selected_user_id,
                            is_active=1 if selected_status == "Active" else 0,
                            actor_username=actor_username
                        )
                        st.success(tr("تم تحديث حالة الحساب.", "Account status updated."))
                        st.rerun()
                    except Exception as exc:
                        st.error(f"{tr('تعذر تحديث حالة الحساب: ', 'Could not update the account status: ')}{exc}")

            st.divider()

            st.markdown("##### " + tr("إعادة تعيين كلمة المرور", "Reset Password"))

            with st.form("reset_password_form"):
                reset_password_value = st.text_input(
                    tr("كلمة المرور الجديدة", "New password"),
                    type="password",
                    key="reset_password_value"
                )

                reset_password_confirm = st.text_input(
                    tr("تأكيد كلمة المرور الجديدة", "Confirm new password"),
                    type="password",
                    key="reset_password_confirm"
                )

                submit_reset = st.form_submit_button(
                    tr("إعادة التعيين", "Reset Password"),
                    width="stretch"
                )

            if submit_reset:
                if len(reset_password_value) < 8:
                    st.error(tr("كلمة المرور يجب أن تكون 8 أحرف على الأقل.", "Password must be at least 8 characters."))
                elif reset_password_value != reset_password_confirm:
                    st.error(tr("كلمتا المرور غير متطابقتين.", "Passwords do not match."))
                else:
                    try:
                        reset_user_password(
                            user_id=selected_user_id,
                            new_password=reset_password_value,
                            actor_username=actor_username
                        )
                        st.success(tr("تم تغيير كلمة المرور بنجاح.", "Password changed."))
                    except Exception as exc:
                        st.error(f"{tr('تعذر تغيير كلمة المرور: ', 'Could not change the password: ')}{exc}")

    with tab_audit_logs:
        st.markdown("##### " + tr("آخر عمليات الأدمن", "Recent Admin Actions"))

        logs_df = get_admin_action_logs(limit=100)

        if logs_df.empty:
            st.warning(tr("لا توجد سجلات عمليات بعد.", "No actions logged yet."))
        else:
            st.dataframe(logs_df, width="stretch", hide_index=True)

            csv_data = logs_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

            st.download_button(
                tr("تحميل سجل العمليات", "Download Audit Log"),
                data=csv_data,
                file_name="admin_action_logs.csv",
                mime="text/csv",
                width="stretch",
                key="download_admin_logs"
            )


def render_approvals_tab():
    """Admin Approval + Merge Staging."""
    section_title(tr("الموافقة على مصادر البيانات", "Source Approval & Staging"))

    st.info(
        tr("يمكن مراجعة مصادر البيانات المعالجة هنا. عند الموافقة على المصدر يتم إنشاء ملف مرحلي فقط، ولا يصبح المصدر متاحًا في صفحة البحث إلا بعد تنفيذ خطوة الدمج النهائية.", "Review processed data sources here. Approving a source only creates a staging file; it reaches the Search page after the final merge step.")
    )

    try:
        review_df = list_sources_for_review()
    except Exception as exc:
        st.error(f"{tr('تعذر تحميل المصادر للمراجعة: ', 'Could not load sources for review: ')}{exc}")
        return

    if review_df.empty:
        st.warning(tr("لا توجد مصادر جاهزة للمراجعة حاليًا.", "No sources waiting for review."))
        return

    st.markdown("##### " + tr("مصادر بانتظار المراجعة", "Sources for Review"))
    st.dataframe(review_df, width="stretch", hide_index=True)

    options = {}

    for _, row in review_df.iterrows():
        source_id = str(row.get("source_id", ""))
        status = str(row.get("status", ""))
        accepted = str(row.get("accepted_rows", ""))
        rejected = str(row.get("rejected_rows", ""))

        label = f"{source_id} | status={status} | accepted={accepted} | rejected={rejected}"
        options[label] = source_id

    selected_label = st.selectbox(
        tr("اختر المصدر", "Select source"),
        list(options.keys()),
        key="selected_source_for_approval"
    )

    selected_source_id = options[selected_label]

    selected_row = review_df[
        review_df["source_id"].astype(str) == str(selected_source_id)
    ]

    if selected_row.empty:
        st.error(tr("المصدر المحدد غير موجود.", "Selected source not found."))
        return

    selected_status = str(selected_row.iloc[0].get("status", "")).lower()

    st.divider()
    st.markdown("##### " + tr("تقارير المصدر", "Source Reports"))

    report_tabs = st.tabs([
        tr("الصفوف المعالجة", "Processed Rows"),
        tr("الصفوف المرفوضة", "Rejected Rows"),
        tr("تقرير التحقق", "Validation Report")
    ])

    with report_tabs[0]:
        try:
            processed_df = load_processed_rows_for_source(selected_source_id)

            if processed_df.empty:
                st.caption(tr("لا يوجد ملف processed أو الملف فارغ.", "No processed file, or it is empty."))
            else:
                st.caption(f"{tr('الصفوف المعالجة: ', 'Processed rows: ')}{len(processed_df)}")
                st.dataframe(processed_df.head(100), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"{tr('تعذر تحميل الصفوف المعالجة: ', 'Could not load processed rows: ')}{exc}")

    with report_tabs[1]:
        try:
            rejected_df = load_rejected_rows_for_source(selected_source_id)

            if rejected_df.empty:
                st.caption(tr("لا توجد صفوف مرفوضة أو التقرير غير موجود.", "No rejected rows, or the report is missing."))
            else:
                st.caption(f"{tr('الصفوف المرفوضة: ', 'Rejected rows: ')}{len(rejected_df)}")
                st.dataframe(rejected_df.head(100), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"{tr('تعذر تحميل الصفوف المرفوضة: ', 'Could not load rejected rows: ')}{exc}")

    with report_tabs[2]:
        try:
            validation_df = load_validation_report_for_source(selected_source_id)

            if validation_df.empty:
                st.caption(tr("تقرير التحقق غير موجود.", "Validation report not found."))
            else:
                st.dataframe(validation_df, width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"{tr('تعذر تحميل تقرير التحقق: ', 'Could not load validation report: ')}{exc}")

    st.divider()
    st.markdown("##### " + tr("قرار الأدمن", "Decision"))

    current_user = get_current_user() or {}
    actor_username = current_user.get("username", "admin")

    notes = st.text_area(
        tr("ملاحظات المراجعة", "Review notes"),
        key="review_notes"
    )

    c1, c2 = st.columns(2)

    with c1:
        approve_disabled = selected_status not in ["processed", "pending_approval", "approved"]

        if st.button(
            tr("موافقة وإنشاء Staging", "Approve & Create Staging"),
            width="stretch",
            key="approve_source_btn",
            disabled=approve_disabled
        ):
            try:
                staging_path = approve_source(
                    source_id=selected_source_id,
                    approved_by=actor_username,
                    notes=notes
                )
                st.success(tr("تمت الموافقة وإنشاء ملف Staging بنجاح.", "Approved; staging file created."))
                st.code(str(staging_path), language="text")
                st.rerun()
            except Exception as exc:
                st.error(f"{tr('فشلت الموافقة: ', 'Approval failed: ')}{exc}")

    with c2:
        reject_disabled = selected_status not in ["processed", "pending_approval", "approved"]

        if st.button(
            tr("رفض المصدر", "Reject Source"),
            width="stretch",
            key="reject_source_btn",
            disabled=reject_disabled
        ):
            try:
                reject_source(
                    source_id=selected_source_id,
                    rejected_by=actor_username,
                    reason=notes if notes else "Rejected by admin."
                )
                st.warning(tr("تم رفض المصدر.", "Source rejected."))
                st.rerun()
            except Exception as exc:
                st.error(f"{tr('فشل الرفض: ', 'Reject failed: ')}{exc}")

    st.divider()

    if st.button(
        tr("تصدير لقطة المراجعة", "Export Review Snapshot"),
        width="stretch",
        key="export_review_snapshot"
    ):
        try:
            snapshot_path = export_review_snapshot()
            st.success(tr("تم تصدير لقطة المراجعة.", "Review snapshot exported."))
            st.code(str(snapshot_path), language="text")
        except Exception as exc:
            st.error(f"{tr('فشل تصدير اللقطة: ', 'Snapshot export failed: ')}{exc}")


def render_online_updates_tab():
    """Controlled Online Source Update through Admin only."""
    project_root = PROJECT_ROOT

    st.markdown(tr("### التحديثات الأونلاين لمصادر البيانات", "### Online data source updates"))

    st.info(
        tr("يمكن للأدمن تشغيل تحديث أونلاين مضبوط من مصدر بيانات علمي. يتم حفظ نسخة خام من المصدر، ثم تمريرها إلى مسار التحقق والتنظيف والمعالجة. لا يتم دمج البيانات في صفحة البحث تلقائيًا، بل تحتاج لاحقًا إلى مراجعة وموافقة ودمج.", "Run a controlled online update from a scientific data source. A raw copy is saved and passed through validation, cleaning and processing. Nothing is merged into Search automatically: it still needs review, approval and merge.")
    )

    st.markdown(tr("#### إعدادات المصدر الأونلاين", "#### Online source settings"))

    gwas_url = st.text_input(
        tr("رابط المصدر الأونلاين", "Online source URL"),
        value=DEFAULT_GWAS_ASSOCIATIONS_URL,
        key="gwas_url"
    )

    c1, c2 = st.columns(2)

    with c1:
        max_lines = st.number_input(
            tr("الحد الأقصى لعدد الأسطر المحمّلة", "Maximum lines to download"),
            min_value=100,
            max_value=20000,
            value=1500,
            step=100,
            key="max_lines"
        )

    with c2:
        max_rows = st.number_input(
            tr("الحد الأقصى للصفوف المعالجة", "Maximum rows to process"),
            min_value=50,
            max_value=5000,
            value=300,
            step=50,
            key="max_rows"
        )

    current_user = get_current_user() or {}
    actor_username = current_user.get("username", "admin")

    if st.button(
        tr("تشغيل التحديث الأونلاين", "Run online update"),
        width="stretch",
        key="run_online_gwas_update"
    ):
        try:
            with st.spinner(tr("جاري تحميل ومعالجة المصدر الأونلاين...", "Downloading and processing the online source...")):
                result = run_gwas_online_update(
                    url=gwas_url,
                    max_lines=int(max_lines),
                    max_rows_for_processing=int(max_rows),
                    uploaded_by=actor_username,
                    notes="Online source update from the admin dashboard. Not merged into Search."
                )

            st.success(tr("تم تنفيذ التحديث الأونلاين وحفظ النتائج.", "Online update finished and saved."))
            st.write(tr("الحالة:", "Status:"), result.get("status"))

            raw_path = result.get("raw_snapshot_path")
            converted_path = result.get("converted_ingestion_path")
            log_path = result.get("online_update_log_path")

            if raw_path:
                st.markdown(tr("**مسار النسخة الخام:**", "**Raw copy path:**"))
                st.code(str(raw_path), language="text")

            if converted_path:
                st.markdown(tr("**مسار الملف المحوّل للمعالجة:**", "**Converted file path:**"))
                st.code(str(converted_path), language="text")

            if log_path:
                st.markdown(tr("**مسار سجل التحديث:**", "**Update log path:**"))
                st.code(str(log_path), language="text")

            pipeline_result = result.get("pipeline_result", {})

            if pipeline_result:
                st.markdown(tr("#### نتيجة المعالجة", "#### Processing result"))
                st.json({
                    "source_id": pipeline_result.get("source_id"),
                    "status": pipeline_result.get("status"),
                    "raw_rows": pipeline_result.get("raw_rows"),
                    "accepted_rows": pipeline_result.get("accepted_rows"),
                    "rejected_rows": pipeline_result.get("rejected_rows"),
                })

            st.rerun()

        except Exception as exc:
            st.error(f"{tr('فشل التحديث الأونلاين: ', 'Online update failed: ')}{exc}")

    st.divider()
    st.markdown(tr("#### سجل آخر مصادر الأونلاين", "#### Recent online sources"))

    try:
        registry_path = project_root / "data" / "metadata" / "data_sources_registry.csv"

        if registry_path.exists():
            registry_df = pd.read_csv(registry_path)

            if "source_type" in registry_df.columns:
                online_df = registry_df[
                    registry_df["source_type"].astype(str).str.lower().isin(
                        ["online_gwas", "online_source", "online"]
                    )
                ].copy()

                if online_df.empty:
                    st.caption(tr("لا توجد مصادر أونلاين مسجلة بعد.", "No online sources recorded yet."))
                else:
                    st.dataframe(online_df.tail(20), width="stretch", hide_index=True)
            else:
                st.caption(tr("لا يوجد عمود source_type داخل سجل مصادر البيانات.", "The registry has no source_type column."))
        else:
            st.caption(tr("ملف سجل مصادر البيانات غير موجود.", "Data source registry file not found."))

    except Exception as exc:
        st.error(f"{tr('تعذر عرض سجل التحديثات: ', 'Could not show the update log: ')}{exc}")


def render_final_merge_tab():
    """Final Merge + Rollback."""
    st.markdown(tr("### الدمج النهائي والتراجع", "### Final merge and rollback"))

    st.info(
        tr("هذه الصفحة مخصصة لتنفيذ الدمج النهائي للمصادر الموافق عليها فقط. قبل الدمج يتم إنشاء نسخة احتياطية من ملف البحث الحالي. بعد الدمج يصبح المصدر نشطًا في صفحة البحث. يمكن تنفيذ التراجع عند الحاجة لاستعادة النسخة السابقة.", "Final merge of approved sources only. A backup of the current search file is made first; after merging, the source is live in Search. Roll back at any time to restore the previous version.")
    )

    current_user = get_current_user() or {}
    actor_username = current_user.get("username", "admin")

    merge_tab, rollback_tab = st.tabs([
        "مصادر جاهزة للدمج",
        "مصادر مدمجة وقابلة للتراجع"
    ])

    with merge_tab:
        st.markdown(tr("#### المصادر الموافق عليها", "#### Approved sources"))

        try:
            approved_df = list_approved_sources()
        except Exception as exc:
            st.error(f"{tr('تعذر تحميل المصادر الموافق عليها: ', 'Could not load approved sources: ')}{exc}")
            return

        if approved_df.empty:
            st.warning(tr("لا توجد مصادر موافق عليها جاهزة للدمج النهائي.", "No approved sources ready to merge."))
        else:
            st.dataframe(approved_df, width="stretch", hide_index=True)

            options = {}

            for _, row in approved_df.iterrows():
                source_id = str(row.get("source_id", ""))
                accepted = str(row.get("accepted_rows", ""))
                staging = str(row.get("staging_path", ""))

                label = f"{source_id} | الصفوف المقبولة={accepted} | staging={bool(staging)}"
                options[label] = source_id

            selected_label = st.selectbox(
                tr("اختر المصدر المراد دمجه", "Source to merge"),
                list(options.keys()),
                key="selected_source_for_merge"
            )

            selected_source_id = options[selected_label]

            st.markdown(tr("#### فحص ملف Staging قبل الدمج", "#### Check the staging file before merging"))

            selected_row = approved_df[
                approved_df["source_id"].astype(str).eq(str(selected_source_id))
            ].iloc[0]

            staging_path_value = str(selected_row.get("staging_path", "")).strip()

            if not staging_path_value:
                st.error(tr("لا يوجد مسار Staging لهذا المصدر.", "This source has no staging path."))
            else:
                staging_path = PROJECT_ROOT / staging_path_value

                try:
                    report = validate_staging_file(staging_path)

                    st.json(report)

                    if report.get("is_valid"):
                        st.success(tr("ملف Staging صالح للدمج النهائي.", "Staging file is valid for merging."))
                    else:
                        st.error(tr("ملف Staging غير صالح للدمج النهائي.", "Staging file is not valid for merging."))

                except Exception as exc:
                    st.error(f"{tr('تعذر فحص ملف Staging: ', 'Could not check the staging file: ')}{exc}")

            merge_notes = st.text_area(
                tr("ملاحظات الدمج", "Merge notes"),
                key="merge_notes"
            )

            confirm_merge = st.checkbox(
                tr("أؤكد تنفيذ الدمج النهائي لهذا المصدر", "I confirm the final merge of this source"),
                key="confirm_final_merge"
            )

            if st.button(
                tr("تنفيذ الدمج النهائي", "Run final merge"),
                width="stretch",
                key="final_merge_button",
                disabled=not confirm_merge
            ):
                try:
                    result = final_merge_source(
                        source_id=selected_source_id,
                        merged_by=actor_username,
                        notes=merge_notes
                    )

                    st.success(tr("تم الدمج النهائي بنجاح. أصبح المصدر نشطًا في صفحة البحث.", "Final merge done. The source is now live in Search."))
                    st.json({
                        "source_id": result.get("source_id"),
                        "status": result.get("status"),
                        "enabled": result.get("enabled"),
                        "rows_after_merge": result.get("rows_after_merge"),
                        "backup_path": str(result.get("backup_path")),
                        "merge_log_path": str(result.get("merge_log_path")),
                    })
                    st.rerun()

                except Exception as exc:
                    st.error(f"{tr('فشل الدمج النهائي: ', 'Final merge failed: ')}{exc}")

    with rollback_tab:
        st.markdown(tr("#### المصادر المدمجة", "#### Merged sources"))

        try:
            merged_df = list_merged_sources()
        except Exception as exc:
            st.error(f"{tr('تعذر تحميل المصادر المدمجة: ', 'Could not load merged sources: ')}{exc}")
            return

        if merged_df.empty:
            st.warning(tr("لا توجد مصادر مدمجة حاليًا.", "No merged sources."))
        else:
            st.dataframe(merged_df, width="stretch", hide_index=True)

            rollback_options = {}

            for _, row in merged_df.iterrows():
                source_id = str(row.get("source_id", ""))
                status = str(row.get("status", ""))
                backup = str(row.get("backup_path", ""))

                label = f"{source_id} | الحالة={status} | backup={bool(backup)}"
                rollback_options[label] = source_id

            selected_rollback_label = st.selectbox(
                tr("اختر المصدر المراد التراجع عنه", "Source to roll back"),
                list(rollback_options.keys()),
                key="selected_source_for_rollback"
            )

            rollback_source_id = rollback_options[selected_rollback_label]

            rollback_notes = st.text_area(
                tr("ملاحظات التراجع", "Rollback notes"),
                key="rollback_notes"
            )

            confirm_rollback = st.checkbox(
                tr("أؤكد تنفيذ التراجع واستعادة النسخة السابقة", "I confirm the rollback and restoring the previous version"),
                key="confirm_rollback"
            )

            if st.button(
                tr("تنفيذ التراجع", "Run rollback"),
                width="stretch",
                key="rollback_button",
                disabled=not confirm_rollback
            ):
                try:
                    result = rollback_source(
                        source_id=rollback_source_id,
                        rollback_by=actor_username,
                        notes=rollback_notes
                    )

                    st.warning(tr("تم تنفيذ التراجع واستعادة النسخة السابقة.", "Rolled back; previous version restored."))
                    st.json({
                        "source_id": result.get("source_id"),
                        "status": result.get("status"),
                        "enabled": result.get("enabled"),
                        "rows_after_rollback": result.get("rows_after_rollback"),
                        "rollback_log_path": str(result.get("rollback_log_path")),
                    })
                    st.rerun()

                except Exception as exc:
                    st.error(f"{tr('فشل التراجع: ', 'Rollback failed: ')}{exc}")

    st.divider()

    if st.button(
        tr("تصدير لقطة حالة الدمج", "Export merge status snapshot"),
        width="stretch",
        key="export_merge_snapshot"
    ):
        try:
            snapshot_path = export_merge_snapshot()
            st.success(tr("تم تصدير لقطة حالة الدمج.", "Merge status snapshot exported."))
            st.code(str(snapshot_path), language="text")
        except Exception as exc:
            st.error(f"{tr('فشل تصدير لقطة الدمج: ', 'Merge snapshot export failed: ')}{exc}")


def render_data_management_review_tab():
    """Admin Dashboard final data management review."""
    project_root = PROJECT_ROOT

    st.markdown(tr("### مراجعة إدارة البيانات", "### Data management review"))

    st.info(
        tr("تعرض هذه الصفحة ملخصًا شاملًا لمسار البيانات داخل المنصة، من رفع المصدر أو جلبه أونلاين، مرورًا بالتحقق والمعالجة والموافقة، ثم الدمج النهائي أو التراجع عند الحاجة.", "An overview of the data workflow: upload or fetch a source, validate, process, approve, then merge or roll back.")
    )

    registry_path = project_root / "data" / "metadata" / "data_sources_registry.csv"
    ranked_path = project_root / "data" / "processed" / "ranked_associations_initial.csv"
    backups_dir = project_root / "data" / "processed" / "backups"
    merge_logs_dir = project_root / "data" / "processed" / "merge_logs"
    outputs_dir = project_root / "outputs" / "tables"

    registry_df = pd.read_csv(registry_path) if registry_path.exists() else pd.DataFrame()
    ranked_df = pd.read_csv(ranked_path) if ranked_path.exists() else pd.DataFrame()

    st.markdown(tr("#### ملخص ملف البحث النشط", "#### Active search file"))

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(tr("صفوف البحث النشط", "Active search rows"), len(ranked_df))
    c2.metric(tr("أعمدة ملف البحث", "Search file columns"), len(ranked_df.columns))
    c3.metric(tr("مصادر البيانات", "Data sources"), len(registry_df))
    c4.metric(
        tr("مصادر نشطة", "Active sources"),
        int(registry_df["status"].astype(str).str.lower().isin(["active", "merged"]).sum())
        if not registry_df.empty and "status" in registry_df.columns else 0
    )

    st.markdown(tr("#### مسار البيانات المعتمد", "#### Data workflow"))

    flow_steps = [
        tr("رفع ملف أو جلب مصدر أونلاين", "Upload a file or fetch an online source"),
        tr("التحقق من الأعمدة والقيم الأساسية", "Validate columns and key values"),
        tr("التنظيف والتوحيد وإزالة التكرار", "Clean, normalize and deduplicate"),
        tr("حفظ مصدر معالج غير نشط", "Save as an inactive processed source"),
        tr("مراجعة الأدمن والموافقة أو الرفض", "Admin review: approve or reject"),
        tr("إنشاء ملف مرحلي Staging", "Create a staging file"),
        tr("الدمج النهائي بعد إنشاء نسخة احتياطية", "Final merge after a backup"),
        tr("ظهور البيانات في البحث أو التراجع عند الحاجة", "Live in Search, or roll back if needed"),
    ]
    arrow = '<div class="flow-arrow">↓</div>'
    flow_html = arrow.join(
        f'<div class="flow-step">{i}. {html.escape(step)}</div>' for i, step in enumerate(flow_steps, 1)
    )
    st.markdown(f'<div class="data-flow-card">{flow_html}</div>', unsafe_allow_html=True)

    st.markdown(tr("#### حالة مصادر البيانات", "#### Data source status"))

    if registry_df.empty:
        st.warning(tr("لا يوجد سجل مصادر بيانات.", "No data source registry found."))
    else:
        status_tab, source_tab, full_tab = st.tabs([
            "حسب الحالة",
            "حسب نوع المصدر",
            "السجل الكامل"
        ])

        with status_tab:
            if "status" in registry_df.columns:
                status_df = registry_df["status"].astype(str).value_counts().reset_index()
                status_df.columns = ["الحالة", "العدد"]
                st.dataframe(status_df, width="stretch", hide_index=True)
            else:
                st.caption(tr("لا يوجد عمود status داخل سجل المصادر.", "The registry has no status column."))

        with source_tab:
            if "source_type" in registry_df.columns:
                source_df = registry_df["source_type"].astype(str).value_counts().reset_index()
                source_df.columns = ["نوع المصدر", "العدد"]
                st.dataframe(source_df, width="stretch", hide_index=True)
            else:
                st.caption(tr("لا يوجد عمود source_type داخل سجل المصادر.", "The registry has no source_type column."))

        with full_tab:
            st.dataframe(registry_df.tail(50), width="stretch", hide_index=True)

    st.markdown(tr("#### ملفات النسخ الاحتياطية وسجلات الدمج", "#### Backups and merge logs"))

    b1, b2 = st.columns(2)

    with b1:
        st.markdown(tr("##### النسخ الاحتياطية", "##### Backups"))
        backup_files = []

        if backups_dir.exists():
            backup_files = sorted(backups_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)

        if backup_files:
            backup_df = pd.DataFrame([
                {
                    "file": p.name,
                    "path": str(p.relative_to(project_root)),
                    "modified_at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "size_kb": round(p.stat().st_size / 1024, 2),
                }
                for p in backup_files[:20]
            ])
            st.dataframe(backup_df, width="stretch", hide_index=True)
        else:
            st.caption(tr("لا توجد نسخ احتياطية مسجلة بعد.", "No backups recorded yet."))

    with b2:
        st.markdown(tr("##### سجلات الدمج والتراجع", "##### Merge and rollback logs"))
        log_files = []

        if merge_logs_dir.exists():
            log_files = sorted(merge_logs_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)

        if log_files:
            log_df = pd.DataFrame([
                {
                    "file": p.name,
                    "path": str(p.relative_to(project_root)),
                    "modified_at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "size_kb": round(p.stat().st_size / 1024, 2),
                }
                for p in log_files[:20]
            ])
            st.dataframe(log_df, width="stretch", hide_index=True)
        else:
            st.caption(tr("لا توجد سجلات دمج أو تراجع بعد.", "No merge or rollback logs yet."))

    st.markdown(tr("#### تصدير تقرير المراجعة", "#### Export review report"))

    if st.button(
        tr("تصدير تقرير مراجعة إدارة البيانات", "Export data management review"),
        width="stretch",
        key="export_data_management_review"
    ):
        try:
            outputs_dir.mkdir(parents=True, exist_ok=True)

            summary_rows = []

            summary_rows.append({
                "section": "active_search",
                "metric": "rows",
                "value": len(ranked_df),
            })

            summary_rows.append({
                "section": "active_search",
                "metric": "columns",
                "value": len(ranked_df.columns),
            })

            if not registry_df.empty and "status" in registry_df.columns:
                for status, count in registry_df["status"].astype(str).value_counts().items():
                    summary_rows.append({
                        "section": "registry_status",
                        "metric": status,
                        "value": int(count),
                    })

            if not registry_df.empty and "source_type" in registry_df.columns:
                for source_type, count in registry_df["source_type"].astype(str).value_counts().items():
                    summary_rows.append({
                        "section": "registry_source_type",
                        "metric": source_type,
                        "value": int(count),
                    })

            report_df = pd.DataFrame(summary_rows)
            report_path = outputs_dir / "data_management_review_from_ui.csv"
            report_df.to_csv(report_path, index=False, encoding="utf-8-sig")

            st.success(tr("تم تصدير تقرير مراجعة إدارة البيانات.", "Data management review exported."))
            st.code(str(report_path), language="text")

        except Exception as exc:
            st.error(f"{tr('تعذر تصدير التقرير: ', 'Could not export the report: ')}{exc}")


def render_glossary_tab():
    """قاموس المصطلحات:"""
    st.markdown(tr("### قاموس المصطلحات الحيوية والجينية", "### Biological and genetic glossary"))

    st.info(
        tr("يعرض هذا القسم المصطلحات الأساسية المستخدمة في المنصة، مع تعريف عربي مبسط وتعريف إنجليزي. يُستخدم هذا القاموس كمرجع موحّد للشرح داخل المنصة، بحيث تكون تفسيرات المصطلحات واضحة ومتسقة وآمنة.", "Core terms used on the platform, with a simple Arabic and an English definition. The glossary is the single reference for explanations, so terms stay clear, consistent and safe.")
    )

    try:
        glossary_df = load_glossary(active_only=True)
    except Exception as exc:
        st.error(f"{tr('تعذر تحميل قاموس المصطلحات: ', 'Could not load the glossary: ')}{exc}")
        return

    if glossary_df.empty:
        st.warning(tr("لا يوجد قاموس مصطلحات حاليًا.", "No glossary available."))
        return

    c1, c2, c3 = st.columns(3)

    c1.metric(tr("عدد المصطلحات", "Terms"), len(glossary_df))
    c2.metric(tr("عدد الفئات", "Categories"), glossary_df["category"].nunique() if "category" in glossary_df.columns else 0)
    c3.metric(
        tr("مصطلحات نشطة", "Active terms"),
        int(glossary_df["is_active"].astype(str).isin(["1", "True", "true"]).sum())
        if "is_active" in glossary_df.columns else len(glossary_df)
    )

    st.markdown(tr("#### البحث في القاموس", "#### Search the glossary"))

    query = st.text_input(
        tr("اكتب مصطلحًا للبحث", "Type a term to search"),
        key="glossary_search_query",
        placeholder=tr("مثال: SNP, p-value, Gene, PRS", "e.g. SNP, p-value, Gene, PRS")
    )

    if query.strip():
        result_df = search_glossary(query)
    else:
        result_df = glossary_df.copy()

    display_cols = [
        "term",
        "arabic_term",
        "category",
        "arabic_definition",
        "simple_explanation",
        "safe_note",
    ]

    display_cols = [c for c in display_cols if c in result_df.columns]

    st.dataframe(
        result_df[display_cols],
        width="stretch",
        hide_index=True
    )

    st.markdown(tr("#### المصطلحات حسب الفئة", "#### Terms by category"))

    if "category" in glossary_df.columns:
        category_df = glossary_df["category"].astype(str).value_counts().reset_index()
        category_df.columns = ["الفئة", tr("عدد المصطلحات", "Terms")]
        st.dataframe(category_df, width="stretch", hide_index=True)

    st.markdown(tr("#### مرجع الشرح الذكي", "#### Reference for AI explanations"))

    st.caption(
        tr("يُستخدم هذا القاموس كمرجع موحّد لتفسير المصطلحات الحيوية والجينية والإحصائية داخل المنصة، بما يساعد المستخدم على فهم نتائج البحث بطريقة أوضح وأكثر أمانًا.", "The glossary is the shared reference for explaining biological, genetic and statistical terms, helping users read results more clearly and safely.")
    )

    if st.button(
        tr("تصدير ملخص القاموس", "Export glossary summary"),
        width="stretch",
        key="export_glossary_summary"
    ):
        try:
            summary_path = export_glossary_summary()
            st.success(tr("تم تصدير ملخص القاموس.", "Glossary summary exported."))
            st.code(str(summary_path), language="text")
        except Exception as exc:
            st.error(f"{tr('تعذر تصدير ملخص القاموس: ', 'Could not export the glossary summary: ')}{exc}")


def render_ai_model_management_tab():
    """AI Model Management tab for local Ollama models."""
    st.markdown(tr("### إدارة نماذج الذكاء الاصطناعي", "### AI model management"))

    status = get_ollama_status()
    models = list_installed_models() if status.get("running") else []
    active_model = get_active_model()
    model_names = [item["name"] for item in models]

    if not active_model and select_best_ollama_model:
        try:
            active_model = select_best_ollama_model().get("selected_model")
        except Exception:
            active_model = None

    active_info = next((item for item in models if item["name"] == active_model), {})
    config = read_config()
    last_ai = config.get("last_ai_response", {})

    if select_best_ollama_model:
        try:
            recommendation = select_best_ollama_model()
        except Exception:
            recommendation = {"selected_model": active_model, "reason": "Default recommendation unavailable.", "benchmarks": []}
    else:
        recommendation = {"selected_model": active_model, "reason": "Default recommendation.", "benchmarks": []}

    ai_ready = bool(status.get("running") and active_model)
    status_label = "Ready" if ai_ready else ("Loading" if status.get("running") else "Error")

    st.markdown(
        """
        <style>
        .ai-status-title-card {
                        background: #FFFFFF;
            border: 1px solid #D9E7FA;
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 8px 22px rgba(20, 62, 130, 0.06);
            margin-bottom: 16px;
        }
        .ai-status-title-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 18px;
            margin-bottom: 6px;
        }
        .ai-status-title-ar {
                        text-align: start;
            color: #0B3978;
            font-size: 1.16rem;
            font-weight: 780;
            line-height: 1.35;
        }
        .ai-status-title-en {
            direction: ltr;
            text-align: left;
            color: #36537E;
            font-size: 1.02rem;
            font-weight: 650;
            line-height: 1.35;
        }
        .ai-status-subtitle {
            color: #4B638A;
            font-size: 0.92rem;
            line-height: 1.6;
            text-align: start;
        }
        .ai-summary-card {
            background: #FFFFFF;
            border: 1px solid #DCE7F7;
            border-radius: 16px;
            padding: 15px 16px 14px;
            min-height: 112px;
            box-shadow: 0 8px 20px rgba(16, 42, 92, 0.055);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .ai-summary-title {
            color: #4B638A;
            font-size: 0.82rem;
            font-weight: 600;
            line-height: 1.35;
            margin-bottom: 8px;
        }
        .ai-summary-value {
            color: #0B3978;
            font-size: 1.16rem;
            font-weight: 720;
            line-height: 1.25;
            word-break: break-word;
        }
        .ai-summary-note {
            color: #7184A8;
            font-size: 0.76rem;
            line-height: 1.35;
            margin-top: 8px;
        }
        </style>
        """ + f"""
        <div class="ai-status-title-card">
            <div class="ai-status-title-row">
                <div class="ai-status-title-ar">{html.escape(tr("لوحة حالة الذكاء الاصطناعي", "AI status"))}</div>
            </div>
            <div class="ai-status-subtitle">
                {html.escape(tr("متابعة خدمة Ollama، والنموذج النشط، والنماذج المحلية المثبتة.",
                                "Ollama service, the active model and installed local models."))}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    def render_ai_summary_card(title: str, value, note: str = "") -> None:
        st.markdown(
            f"""
            <div class="ai-summary-card">
                <div>
                    <div class="ai-summary-title">{html.escape(str(title))}</div>
                    <div class="ai-summary-value">{html.escape(str(value))}</div>
                </div>
                <div class="ai-summary-note">{html.escape(str(note))}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_ai_summary_card("AI Status", status_label, "حالة المساعد الذكي")
    with c2:
        render_ai_summary_card("Ollama Service", status.get("status", "Checking..."), "الخدمة المحلية")
    with c3:
        render_ai_summary_card("Current Active Model", active_model or "Not selected", "النموذج المستخدم حاليا")
    with c4:
        render_ai_summary_card("Installed Models", len(models), "عدد النماذج المثبتة")

    c5, c6 = st.columns([1.4, 1])
    with c5:
        st.markdown("##### " + tr("النموذج النشط الحالي", "Current Active Model"))
        if active_model:
            st.write(tr("النموذج:", "Model:"), active_model)
            st.write(tr("العائلة:", "Family:"), active_info.get("family", ""))
            st.write(tr("عدد المعاملات:", "Parameters:"), active_info.get("parameters", ""))
            st.write(tr("الحجم:", "Size:"), active_info.get("size", ""))
            st.write(tr("آخر تعديل:", "Modified:"), active_info.get("modified_at", ""))
        else:
            st.warning(tr("لم يتم اختيار نموذج بعد.", "No model selected yet."))

    with c6:
        st.markdown("##### " + tr("النموذج الموصى به", "Recommended Model"))
        st.success(recommendation.get("selected_model") or "Gemma 3")
        st.caption(recommendation.get("reason") or tr("سريع، يدعم العربية، ومناسب للتشغيل المحلي.", "Fast inference, Arabic support, suitable for local execution."))
        if last_ai:
            st.write(tr("زمن آخر استجابة:", "Last response time:"), last_ai.get("elapsed_seconds", ""))
            st.write(tr("آخر طلب ناجح:", "Last successful request:"), last_ai.get("updated_at", ""))
        else:
            st.write(tr("آخر استجابة: لا توجد طلبات بعد", "Last AI Response: No requests yet"))

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(tr("تحديث الحالة", "Refresh Status"), width="stretch", key="ai_model_refresh_status"):
            st.rerun()
    with b2:
        if st.button(tr("تحديث النماذج", "Refresh Installed Models"), width="stretch", key="ai_model_refresh_models"):
            st.rerun()
    with b3:
        if st.button(tr("اختبار النموذج النشط", "Test Active Model"), width="stretch", key="ai_model_test_active"):
            if active_model:
                with st.spinner(tr("جارٍ اختبار النموذج النشط...", "Testing active model...")):
                    result = test_model(active_model)
                if result.get("ok"):
                    st.success(f"{tr('يعمل | ', 'Working | ')}{result.get('elapsed_seconds')}{tr(' ثانية', ' seconds')}")
                    config["last_ai_response"] = {
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                        "model": active_model,
                    }
                    from core.ai.model_manager import write_config
                    write_config(config)
                    st.caption(result.get("response", ""))
                else:
                    st.error(f"{tr('فشل: ', 'Failed: ')}{result.get('message')}")
            else:
                st.warning(tr("اختر نموذجًا نشطًا أولًا.", "Select an active model first."))

    section_title(tr("النماذج المثبتة", "Installed Models"))

    if not status.get("running"):
        st.error(f"{tr('خدمة Ollama غير متاحة: ', 'Ollama service is not available: ')}{status.get('error')}")
    elif not models:
        st.warning(tr("لم يُعثر على نماذج Ollama محلية.", "No local Ollama models were detected."))
    else:
        rows = []
        for item in models:
            is_active = item["name"] == active_model
            rows.append({
                "Active": "Active" if is_active else "Available",
                "Model Name": item["name"],
                "Family": item.get("family", ""),
                "Parameters": item.get("parameters", ""),
                "Size": item.get("size", ""),
                "Modified Date": item.get("modified_at", ""),
                "Context Length": item.get("context_length", ""),
                "Status": item.get("status", "Installed"),
                "Test": "Use button below",
                "Select": "Use selector below",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    section_title(tr("تغيير النموذج النشط", "Change Active Model"))
    selected_model = st.selectbox(
        tr("اختر النموذج المثبت", "Select installed model"),
        model_names if model_names else [""],
        index=model_names.index(active_model) if active_model in model_names else 0,
        key="ai_model_selected_model",
    )

    a1, a2 = st.columns(2)
    with a1:
        if st.button(tr("تطبيق النموذج", "Apply Model"), width="stretch", key="ai_model_apply"):
            result = set_active_model(selected_model)
            if result.get("ok"):
                st.success(result.get("message"))
                st.info(tr("سيستخدم الشرح الذكي هذا النموذج مباشرة.", "AI Explanation will use this model immediately."))
            else:
                st.error(result.get("message"))
    with a2:
        if st.button(tr("اختبار النموذج المحدد", "Test Selected Model"), width="stretch", key="ai_model_test_selected"):
            with st.spinner(tr("جارٍ اختبار النموذج المحدد...", "Testing selected model...")):
                result = test_model(selected_model)
            if result.get("ok"):
                st.success(f"{tr('يعمل | ', 'Working | ')}{result.get('elapsed_seconds')}{tr(' ثانية', ' seconds')}")
                st.caption(result.get("response", ""))
            else:
                st.error(f"{tr('فشل: ', 'Failed: ')}{result.get('message')}")

    if recommendation.get("benchmarks"):
        section_title(tr("نتائج قياس الأداء", "Benchmark Results"))
        st.dataframe(pd.DataFrame(recommendation.get("benchmarks")), width="stretch", hide_index=True)

    section_title(tr("تثبيت نموذج Ollama جديد", "Install New Ollama Model"))
    model_to_install = st.text_input(
        tr("اسم النموذج", "Model name"),
        placeholder=tr("gemma3:latest أو qwen3:latest", "gemma3:latest or qwen3:latest"),
        key="ai_model_install_name",
    )
    if st.button(tr("تثبيت", "Install"), width="stretch", key="ai_model_install_button"):
        model_to_install = model_to_install.strip()
        if not validate_model_name(model_to_install):
            st.error(tr("اسم النموذج غير صالح. أدخل اسم نموذج Ollama صحيح.", "Invalid model name. Enter a valid Ollama model name."))
        elif model_to_install in model_names:
            st.warning(tr("هذا النموذج مثبت مسبقًا.", "This model is already installed."))
        else:
            with st.spinner(f"{tr('جارٍ تنفيذ ollama pull ', 'Running ollama pull ')}{model_to_install} ..."):
                result = install_model(model_to_install)
            if result.get("ok"):
                st.success(result.get("message"))
                st.rerun()
            else:
                st.error(result.get("message"))
                if result.get("output"):
                    st.code(result.get("output"), language="text")

def render_admin_dashboard_page():
    page_header(
        "Admin dashboard",
        "لوحة الإدارة",
        "Accounts, data sources and their review workflow, glossary and AI models.",
        "إدارة الحسابات، ومصادر البيانات ومسار مراجعتها، والقاموس، ونماذج الذكاء الاصطناعي.",
        icon="🛡️",
    )

    tab_overview, tab_users, tab_community, tab_data, tab_glossary, tab_ai = st.tabs([
        tr("📊 نظرة عامة", "📊 Overview"),
        tr("👥 المستخدمون", "👥 Users"),
        tr("💬 المكتبة والمجتمع", "💬 Library & community"),
        tr("🗂️ إدارة البيانات", "🗂️ Data management"),
        tr("📖 قاموس المصطلحات", "📖 Glossary"),
        tr("🧠 الذكاء الاصطناعي", "🧠 AI models"),
    ])

    with tab_overview:
        render_overview_tab()
    with tab_users:
        render_users_tab()
    with tab_community:
        render_community_admin_tab()
    with tab_data:
        notice(tr(
            "مسار البيانات: رفع المصدر أو جلبه ← التحقق ← الموافقة ← الدمج النهائي (مع إمكانية التراجع).",
            "Data workflow: upload or fetch a source → validate → approve → final merge (with rollback).",
        ))
        steps = st.tabs([
            tr("المصادر", "Sources"), tr("التحقق", "Validation"), tr("الموافقات", "Approvals"),
            tr("التحديث من الإنترنت", "Online updates"), tr("الدمج والتراجع", "Merge & rollback"),
            tr("مراجعة شاملة", "Review"), tr("الملفات", "Files"), tr("التشغيل", "Run"),
        ])
        with steps[0]:
            render_sources_tab()
        with steps[1]:
            render_validation_tab()
        with steps[2]:
            render_approvals_tab()
        with steps[3]:
            render_online_updates_tab()
        with steps[4]:
            render_final_merge_tab()
        with steps[5]:
            render_data_management_review_tab()
        with steps[6]:
            render_files_tab()
        with steps[7]:
            render_run_controls_tab()
    with tab_glossary:
        render_glossary_tab()
    with tab_ai:
        render_ai_model_management_tab()
