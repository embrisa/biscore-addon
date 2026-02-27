local addon = BiScore

local function isEquippable(link)
    if not link then
        return false
    end
    local _, _, _, _, _, _, _, _, equipLoc = GetItemInfo(link)
    return equipLoc and equipLoc ~= "" and equipLoc ~= "INVTYPE_BAG" and equipLoc ~= "INVTYPE_NON_EQUIP_IGNORE"
end

local function getPrimarySlotForItem(link)
    if not link then
        return nil
    end
    local _, _, _, _, _, _, _, _, equipLoc = GetItemInfo(link)
    if not equipLoc then
        return nil
    end

    local map = {
        INVTYPE_HEAD = 1,
        INVTYPE_NECK = 2,
        INVTYPE_SHOULDER = 3,
        INVTYPE_CHEST = 5,
        INVTYPE_ROBE = 5,
        INVTYPE_WAIST = 6,
        INVTYPE_LEGS = 7,
        INVTYPE_FEET = 8,
        INVTYPE_WRIST = 9,
        INVTYPE_HAND = 10,
        INVTYPE_FINGER = 11,
        INVTYPE_TRINKET = 13,
        INVTYPE_CLOAK = 15,
        INVTYPE_WEAPON = 16,
        INVTYPE_WEAPONMAINHAND = 16,
        INVTYPE_WEAPONOFFHAND = 17,
        INVTYPE_SHIELD = 17,
        INVTYPE_HOLDABLE = 17,
        INVTYPE_2HWEAPON = 16,
        INVTYPE_RANGED = 18,
        INVTYPE_RANGEDRIGHT = 18,
        INVTYPE_THROWN = 18,
        INVTYPE_RELIC = 18,
    }
    return map[equipLoc]
end

local function appendItemTooltipScore(tooltip, itemLink)
    if not itemLink or not isEquippable(itemLink) then
        return
    end

    local profileKey = addon:GetProfileKeyForUnit("player")
    local _, classToken = UnitClass("player")
    if not profileKey or not classToken then
        return
    end
    local phase = addon:GetCurrentPhase()
    local profileData = addon:GetProfileData(classToken, profileKey, phase)
    if not profileData then
        return
    end

    local slotID = getPrimarySlotForItem(itemLink)
    if not slotID then
        return
    end

    local score = addon:GetUnitBiScore("player")
    if not score then
        return
    end

    tooltip:AddLine(string.format("|cff33ff99BiScore|r: %d / %d (%.1f%%)", score.score, score.maxScore, score.percent * 100))
    tooltip:Show()
end

local function appendUnitTooltipScore(tooltip)
    local _, unit = tooltip:GetUnit()
    if not unit then
        return
    end

    if UnitIsUnit(unit, "player") then
        local selfScore = addon:GetUnitBiScore("player")
        if selfScore then
            tooltip:AddLine(string.format("|cff33ff99BiScore|r: %d / %d (%.1f%%)", selfScore.score, selfScore.maxScore, selfScore.percent * 100))
        end
        tooltip:Show()
        return
    end

    if not UnitIsPlayer(unit) or not CanInspect(unit) then
        return
    end

    tooltip:AddLine("|cff33ff99BiScore|r: Loading...")
    tooltip:Show()

    local guid = UnitGUID(unit)
    addon:InspectUnit(unit, function(result)
        if not GameTooltip:IsShown() then
            return
        end
        local _, currentUnit = GameTooltip:GetUnit()
        if not currentUnit or UnitGUID(currentUnit) ~= guid then
            return
        end
        if result then
            GameTooltip:AddLine(string.format("|cff33ff99BiScore|r: %d / %d (%.1f%%)", result.score, result.maxScore, result.percent * 100))
        else
            GameTooltip:AddLine("|cff33ff99BiScore|r: N/A")
        end
        GameTooltip:Show()
    end)
end

function addon:InitTooltip()
    GameTooltip:HookScript("OnTooltipSetItem", function(tooltip)
        local _, link = tooltip:GetItem()
        appendItemTooltipScore(tooltip, link)
    end)
    ItemRefTooltip:HookScript("OnTooltipSetItem", function(tooltip)
        local _, link = tooltip:GetItem()
        appendItemTooltipScore(tooltip, link)
    end)
    GameTooltip:HookScript("OnTooltipSetUnit", function(tooltip)
        appendUnitTooltipScore(tooltip)
    end)
end
