"""Cursor pagination for every list endpoint.

Offset pagination breaks on the delivery feed: during harvest peak new rows arrive at the top
while a phone is paging, so offset pages shift (duplicates and skipped rows) and `OFFSET n` gets
slower as the table grows. A cursor encodes a position in a stable ordering instead.
"""

from rest_framework.pagination import CursorPagination


class CreatedAtCursorPagination(CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    # `id` breaks ties between rows created in the same microsecond.
    ordering = ("-created_at", "-id")


class DeliveryFeedPagination(CreatedAtCursorPagination):
    # Backed by the composite index Delivery(washing_station, -recorded_at, -id).
    ordering = ("-recorded_at", "-id")
