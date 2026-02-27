local addon = BiScore

local function ensureLabel()
    if BiScoreCharacterLabel then
        return BiScoreCharacterLabel
    end
    local font = CharacterNameText:GetFont()
    local label = CharacterFrame:CreateFontString("BiScoreCharacterLabel", "OVERLAY", "GameFontNormal")
    label:SetFont(font, 12, "OUTLINE")
    label:SetPoint("TOPLEFT", CharacterNameText, "BOTTOMLEFT", 0, -4)
    label:SetTextColor(0.2, 1.0, 0.6)
    return label
end

function addon:RefreshCharacterScore()
    if not CharacterFrame then
        return
    end
    local label = ensureLabel()
    local result = self:GetUnitBiScore("player")
    if not result then
        label:SetText("BiScore: N/A")
        return
    end
    label:SetText(string.format("BiScore: %d / %d  |  BiS: %d/%d", result.score, result.maxScore, result.bisSlotCount, result.totalSlots))
end

function addon:InitCharacterFrame()
    CharacterFrame:HookScript("OnShow", function()
        addon:RefreshCharacterScore()
    end)
end
