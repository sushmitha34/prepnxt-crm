from rest_framework.pagination import PageNumberPagination


class LeadPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"  # allows ?page_size=100 if ever needed
    max_page_size = 200