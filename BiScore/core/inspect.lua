local addon = BiScore

function addon:InitInspectQueue()
    self.inspectQueue = {}
    self.inspectPending = nil
end

local function unitGuid(unit)
    if not unit or not UnitExists(unit) then
        return nil
    end
    return UnitGUID(unit)
end

local function canInspect(unit)
    return unit and UnitExists(unit) and CanInspect(unit) and not UnitIsUnit(unit, "player")
end

function addon:ProcessInspectQueue()
    if self.inspectPending then
        return
    end
    local nextEntry = table.remove(self.inspectQueue, 1)
    if not nextEntry then
        return
    end

    if not canInspect(nextEntry.unit) then
        if nextEntry.callback then
            nextEntry.callback(nil)
        end
        C_Timer.After(0.2, function() addon:ProcessInspectQueue() end)
        return
    end

    self.inspectPending = {
        unit = nextEntry.unit,
        guid = unitGuid(nextEntry.unit),
        callback = nextEntry.callback,
    }
    NotifyInspect(nextEntry.unit)
end

function addon:InspectUnit(unit, onReady)
    table.insert(self.inspectQueue, { unit = unit, callback = onReady })
    self:ProcessInspectQueue()
end

function addon:OnInspectReady(guid)
    local pending = self.inspectPending
    if not pending then
        return
    end
    if guid ~= pending.guid then
        return
    end

    local result = self:GetUnitBiScore(pending.unit)
    if pending.callback then
        pending.callback(result)
    end
    ClearInspectPlayer()
    self.inspectPending = nil
    C_Timer.After(1.5, function() addon:ProcessInspectQueue() end)
end
