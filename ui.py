import time
from html import escape

import streamlit as st

from generation import build_markdown_filename, build_output_filename
from logger import format_elapsed


def inject_ui_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --accent-main: #19c6b7;
            --accent-strong: #0ea5a8;
            --accent-soft: rgba(25, 198, 183, 0.14);
            --accent-border: rgba(45, 212, 191, 0.38);
            --text-soft: rgba(226, 232, 240, 0.82);
        }

        .stButton > button,
        .stDownloadButton > button {
            background: linear-gradient(135deg, var(--accent-main), var(--accent-strong)) !important;
            border: 1px solid var(--accent-border) !important;
            color: #052a2b !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--accent-main) !important;
            color: #031b1c !important;
        }

        div[data-testid="stProgressBar"] > div > div > div > div {
            background: linear-gradient(90deg, var(--accent-main), #67e8f9) !important;
        }

        div[data-baseweb="notification"] {
            background: var(--accent-soft) !important;
            border: 1px solid var(--accent-border) !important;
            border-radius: 14px !important;
        }

        div[data-baseweb="notification"] * {
            color: #d9fffb !important;
        }

        .live-status-card {
            background: linear-gradient(180deg, rgba(10, 18, 28, 0.95), rgba(8, 15, 24, 0.88));
            border: 1px solid var(--accent-border);
            border-radius: 16px;
            padding: 16px 18px;
            margin: 8px 0 14px 0;
            box-shadow: 0 10px 30px rgba(8, 145, 178, 0.12);
        }

        .live-status-title {
            color: #e6fffb;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .live-status-stage {
            color: #99f6e4;
            font-size: 0.95rem;
            margin-bottom: 10px;
        }

        .live-status-meta {
            color: var(--text-soft);
            font-size: 0.88rem;
            line-height: 1.55;
        }

        .activity-feed {
            border: 1px solid rgba(45, 212, 191, 0.22);
            border-radius: 14px;
            padding: 12px 14px;
            background: rgba(15, 23, 42, 0.42);
        }

        .activity-feed-title {
            color: #d5fffb;
            font-size: 0.92rem;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .activity-feed-item {
            color: var(--text-soft);
            font-size: 0.88rem;
            margin: 4px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_live_status(target=None) -> None:
    status = st.session_state.processing_status
    activity_feed = st.session_state.activity_feed
    if not status and not activity_feed:
        return

    sink = target if target is not None else st
    with sink.container():
        started_at = status.get("started_at")
        elapsed = format_elapsed(time.time() - started_at) if started_at else "00:00"
        current_block = int(status.get("current_block") or 0)
        block_count = int(status.get("block_count") or 0)
        target_chars = int(status.get("target_chars") or 0)
        context_chars = int(status.get("context_chars") or 0)
        title = "Идет обработка" if status.get("is_running") else "Состояние"
        stage = escape(str(status.get("stage") or "Ожидание"))
        detail = escape(str(status.get("detail") or ""))
        st.markdown(
            f"""
            <div class="live-status-card">
                <div class="live-status-title">{title}</div>
                <div class="live-status-stage">{stage}</div>
                <div class="live-status-meta">{detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        metric_columns = st.columns(4)
        metric_columns[0].metric("Блок", f"{current_block}/{block_count}" if block_count else "0/0")
        metric_columns[1].metric("Цель", f"{target_chars} симв.")
        metric_columns[2].metric("Контекст", f"{context_chars} симв.")
        metric_columns[3].metric("Прошло", elapsed)
        progress_value = float(status.get("progress") or 0.0)
        st.progress(progress_value)
        st.caption("Если текущий блок обрабатывается долго, это нормально: ответ OpenAI может занимать десятки секунд.")

        if activity_feed:
            items = "".join(
                f"<div class=\"activity-feed-item\">{escape(entry['time'])}  {escape(entry['message'])}</div>"
                for entry in activity_feed[-5:]
            )
            st.markdown(
                f"""
                <div class="activity-feed">
                    <div class="activity-feed-title">Последние события</div>
                    {items}
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_run_log(target=None) -> None:
    if not st.session_state.run_log:
        return

    sink = target if target is not None else st
    with sink.container():
        with st.expander("Журнал обработки", expanded=True):
            max_block_count = max(
                (entry["block_count"] for entry in st.session_state.run_log if entry["block_count"]),
                default=1,
            )
            completed_steps = sum(1 for entry in st.session_state.run_log if entry["status"] in {"OK", "DONE"})
            progress_value = min(1.0, completed_steps / max_block_count) if max_block_count else 0.0
            st.progress(progress_value)
            status = st.session_state.processing_status
            st.caption(f"Этап: {status['stage']} | {status['detail']}")
            for entry in st.session_state.run_log:
                st.write(
                    f"[{entry['status']}] Блок {entry['block_index']}/{entry['block_count']} | "
                    f"цель: {entry['target_chars']} симв. | контекст: {entry['context_chars']} симв. | {entry['details']}"
                )
            st.caption(st.session_state.last_log_hint)


def render_sidebar(config: dict[str, object]) -> tuple[str, int, int]:
    st.sidebar.header("Настройки")
    model_options = [*config["model_options"], "custom"]
    default_model = str(config["default_model"])
    default_index = model_options.index(default_model) if default_model in model_options else 0
    selected_model = st.sidebar.selectbox("Модель", model_options, index=default_index)
    custom_model = ""
    if selected_model == "custom":
        custom_model = st.sidebar.text_input("Имя модели", value=default_model).strip()

    model = custom_model or selected_model
    chunk_size = st.sidebar.slider(
        "Размер целевого блока, символов",
        min_value=3000,
        max_value=12000,
        value=int(config["chunk_size"]),
        step=500,
    )
    max_retries = st.sidebar.slider(
        "Количество retry",
        min_value=1,
        max_value=5,
        value=int(config["max_retries"]),
    )
    return model, chunk_size, max_retries


def render_markdown_preview(target=None, *, title: str) -> None:
    blocks = st.session_state.processed_block_markdowns
    if not blocks:
        return

    sink = target if target is not None else st
    option_count = len(blocks)
    if st.session_state.markdown_preview_block_index > option_count:
        st.session_state.markdown_preview_block_index = option_count

    with sink.container():
        with st.expander(title, expanded=False):
            st.caption("На экране показывается только один Markdown-блок, чтобы интерфейс не перегружался на больших документах.")
            selected_block = st.selectbox(
                "Показать блок",
                options=list(range(1, option_count + 1)),
                index=max(0, st.session_state.markdown_preview_block_index - 1),
                key="markdown_preview_block_select",
            )
            st.session_state.markdown_preview_block_index = selected_block
            st.text_area(
                "Markdown блока",
                value=blocks[selected_block - 1],
                height=320,
            )


def render_result(docx_bytes: bytes, markdown_text: str, original_filename: str) -> None:
    st.success("Документ обработан.")
    st.download_button(
        label="Скачать итоговый DOCX",
        data=docx_bytes,
        file_name=build_output_filename(original_filename),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать итоговый Markdown",
        data=markdown_text.encode("utf-8"),
        file_name=build_markdown_filename(original_filename),
        mime="text/markdown",
        use_container_width=True,
    )
    render_markdown_preview(title="Предпросмотр Markdown")


def render_partial_result() -> None:
    markdown_text = st.session_state.latest_markdown
    if not markdown_text or st.session_state.latest_docx_bytes is not None:
        return

    source_name = st.session_state.latest_source_name or "result.docx"
    st.warning("Доступен промежуточный Markdown-результат последнего запуска.")
    st.download_button(
        label="Скачать текущий Markdown",
        data=markdown_text.encode("utf-8"),
        file_name=build_markdown_filename(source_name),
        mime="text/markdown",
        use_container_width=True,
    )
