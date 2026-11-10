# Wird von den Build-Jobs mit "source" eingebunden: legt das Release an
# (falls es noch nicht existiert) und setzt Titel + Beschreibung.
# Ergebnis: Variable TAG mit dem Release-Namen.

PRE=""
if [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    TAG="$GITHUB_REF_NAME"
elif [ "${GITHUB_REF_NAME:-}" = "xtouch" ]; then
    TAG="$BETA_VERSION"            # test build of the X-Touch branch
    PRE="--prerelease"
else
    TAG="$RELEASE_VERSION"
fi
TITLE="MPC Mapper $TAG für macOS und Windows"
NOTES=packaging/release-notes.md
if [ -n "$PRE" ]; then
    TITLE="MPC Mapper $TAG (Testversion mit X-Touch Compact)"
    NOTES=packaging/beta-notes.md
fi

# Mehrere Builds laufen parallel – wer zuerst kommt, legt das Release an.
if ! gh release view "$TAG" >/dev/null 2>&1; then
    gh release create "$TAG" --target "$GITHUB_SHA" --title "$TITLE" $PRE \
        --notes-file "$NOTES" || sleep 15
fi
gh release edit "$TAG" --title "$TITLE" --notes-file "$NOTES" $PRE
