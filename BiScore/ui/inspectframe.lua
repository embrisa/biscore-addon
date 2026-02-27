local addon = BiScore

local function ensureInspectLabel()
    if BiScoreInspectLabel then
        return BiScoreInspectLabel
    end
    local label = InspectFrame:CreateFontString("BiScoreInspectLabel", "OVERLAY", "GameFontNormal")
    label:SetPoint("TOPLEFT", InspectNameText, "BOTTOMLEFT", 0, -4)
    label:SetTextColor(0.2, 1.0, 0.6)
    return label
end

function addon:InitInspectFrame()
    InspectFrame:HookScript("OnShow", function()
        local unit = InspectFrame.unit
        if not unit then
            return
        end
        local label = ensureInspectLabel()
        label:SetText("BiScore: Loading...")
        addon:InspectUnit(unit, function(result)
            if not InspectFrame:IsShown() then
                return
            end
            if not result then
                label:SetText("BiScore: N/A")
                return
            end
            label:SetText(string.format("BiScore: %d / %d (%.1f%%)  |  BiS: %d/%d", result.score, result.maxScore, result.percent * 100, result.bisSlotCount, result.totalSlots))
        end)
    end)
end
