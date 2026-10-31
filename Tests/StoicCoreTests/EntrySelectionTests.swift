import Testing
@testable import StoicCore

struct EntrySelectionTests {
    let ids = ["a", "b", "c", "d", "e"]
    @Test func plainClickReplacesAndCommandToggles() {
        #expect(EntrySelection.selecting("c", in: ids, selected: ["a", "b"], anchor: "a", extending: false, toggling: false) == ["c"])
        #expect(EntrySelection.selecting("c", in: ids, selected: ["a"], anchor: "a", extending: false, toggling: true) == ["a", "c"])
        #expect(EntrySelection.selecting("a", in: ids, selected: ["a", "c"], anchor: "a", extending: false, toggling: true) == ["c"])
    }
    @Test func shiftUsesDisplayOrderAndPreservesAnchorWhenShrinking() {
        #expect(EntrySelection.selecting("d", in: ids, selected: ["b"], anchor: "b", extending: true, toggling: false) == ["b", "c", "d"])
        #expect(EntrySelection.selecting("c", in: ids, selected: ["b", "c", "d"], anchor: "b", extending: true, toggling: false) == ["b", "c"])
        #expect(EntrySelection.selecting("a", in: ids.reversed(), selected: ["c"], anchor: "c", extending: true, toggling: false) == ["a", "b", "c"])
    }
    @Test func commandShiftAddsRangeAndMissingAnchorFallsBack() {
        #expect(EntrySelection.selecting("e", in: ids, selected: ["a"], anchor: "d", extending: true, toggling: true) == ["a", "d", "e"])
        #expect(EntrySelection.selecting("c", in: ids, selected: ["a"], anchor: "hidden", extending: true, toggling: false) == ["c"])
    }
}
