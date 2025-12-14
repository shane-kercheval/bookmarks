- when someone deletes a bookmark, we should capture the timestamp which marks it as deleted
    - in the future there will be a background job that permanently removes bookmarks that have been in the "deleted" state for over 30 days
    - but for now, deleted bookmarks will be hidden from the main bookmarks list (and search results), but in the frontend we should have a way for users to view and restore deleted bookmarks within that 30-day window
- similarly we want archive functionality
    - when someone archives a bookmark, we capture the timestamp marking it as archived
    - archived bookmarks are hidden from the main list and search results unless the user explicitly opts to view archived bookmarks
    - archived bookmarks are are a way to say "i don't really want to delete this because it may be useful in the future, but i don't need to see it in my main list or search results right now"
- both deleted and archived bookmarks should still be stored in the database, just with appropriate flags/timestamps
- we will need to update the database schema to add `deleted_at` and `archived_at` timestamp columns to the bookmarks table
- we will need to update the API endpoints for fetching bookmarks to filter out deleted/archived bookmarks by default
- we will need to add new API endpoints to allow users to view and restore deleted bookmarks, and to view/unarchive archived bookmarks
- we will need to update the frontend to add UI for viewing/restoring deleted bookmarks and viewing/unarchiving archived bookmarks

- Given this, the frontend no longer has to prompt confirmation when archiving or deleting a bookmark. Instead, it can simply show a toast notification with an "Undo" option that allows the user to quickly restore the bookmark if they acted by mistake. Or they can go to the "Deleted Bookmarks" or "Archived Bookmarks" view to manage those bookmarks.


