# Wird von den Build-Jobs mit "source" eingebunden: legt das Release an
# (falls es noch nicht existiert) und setzt Titel + Beschreibung.
# Ergebnis: Variable TAG mit dem Release-Namen.

if [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    TAG="$GITHUB_REF_NAME"
else
    TAG="$RELEASE_VERSION"
fi
TITLE="MPC Mapper $TAG für macOS und Windows"

# Mehrere Builds laufen parallel – wer zuerst kommt, legt das Release an.
if ! gh release view "$TAG" >/dev/null 2>&1; then
    gh release create "$TAG" --target "$GITHUB_SHA" --title "$TITLE" \
        --notes-file packaging/release-notes.md || sleep 15
fi
gh release edit "$TAG" --title "$TITLE" --notes-file packaging/release-notes.md
