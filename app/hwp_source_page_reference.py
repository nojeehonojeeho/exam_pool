"""Resolve the physical reference page in the correct input document role."""


def reference_page(item, role, page_count):
    if role == 'solution':
        pages = item.get('source_solution_pages')
        if not isinstance(pages, list) or not pages:
            raise ValueError('SOLUTION_SOURCE_PAGE_MISSING')
        page = pages[0]
    elif role in ('problem', 'endnote'):
        page = item.get('source_page')
    else:
        raise ValueError('UNSUPPORTED_SOURCE_PAGE_ROLE')
    if type(page) is not int or not 1 <= page <= page_count:
        raise ValueError('SOURCE_PAGE_OUT_OF_RANGE')
    return page
