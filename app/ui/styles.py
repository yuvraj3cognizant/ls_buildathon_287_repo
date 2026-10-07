"""Global CSS for the app. Injected once per run from streamlit_app.main().

Colours themselves live in .streamlit/config.toml; this only handles layout
and typography that the theme options can't express.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
/* Headings in a serif face, a more editorial and less "dashboard" feel. */
h1, h2, h3, h4 {
    font-family: Georgia, "Source Serif Pro", "Times New Roman", serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
    color: #1F3B3D;
}
h1 { font-size: 2rem !important; }

/* Keep the reading column comfortable instead of edge-to-edge. Scoped to the
   main column only; a bare .block-container rule also hits other containers. */
[data-testid="stMainBlockContainer"] { max-width: 1100px; padding-top: 2.5rem; }

/* The scroll area is a fixed-height (100dvh) flex column. Its children must
   never shrink: if the main column collapses to the viewport height, its
   content spills past it and the sticky chat input floats mid-page. */
[data-testid="stAppScrollToBottomContainer"] > * { flex-shrink: 0; }

/* Chat bubbles: soft card for the assistant, plain for the user. */
[data-testid="stChatMessage"] {
    border-radius: 10px;
    padding: 0.9rem 1rem;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #FFFFFF;
    border: 1px solid #E6E0D5;
}

/* Sidebar footer pinned to the bottom. Stretch each level of the sidebar
   down to the full height, then push the footer down with margin-top:auto.
   The footer's flex item is the stLayoutWrapper around the keyed container,
   so the footer rules go on that. */
[data-testid="stSidebarContent"] { display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] {
    flex: 1 0 auto;
    display: flex;
    flex-direction: column;
    padding-bottom: 0 !important;
}
[data-testid="stSidebarUserContent"] > div { flex: 1 0 auto; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { flex: 1 0 auto; }
[data-testid="stLayoutWrapper"]:has(> .st-key-sidebar_footer) {
    margin-top: auto;
    position: sticky;
    bottom: 0;
    z-index: 2;
    background: #F0ECE4;
    border-top: 1px solid #DDD6C9;
    padding: 0.75rem 0 1rem 0;
}

/* Chat list buttons read like a list, not a stack of buttons. */
.st-key-chat_list button {
    justify-content: flex-start;
    border: none;
    background: transparent;
    font-size: 0.92rem;
    padding: 0.35rem 0.6rem;
    min-height: 0;
}
.st-key-chat_list button > div { justify-content: flex-start; width: 100%; min-width: 0; }
.st-key-chat_list button p {
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.st-key-chat_list button:hover { background: #E6E0D5; }
.st-key-chat_list button:disabled {
    background: #E1EBEA;
    color: #1F3B3D;
    font-weight: 600;
    opacity: 1;
}
</style>
"""


def inject_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
