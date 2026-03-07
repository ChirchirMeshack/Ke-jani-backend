from rest_framework.response import Response

def custom_response(data=None, message="Success", status="success", status_code=200):   
    """
    Custom response function to standardize API responses.
    
    :param data: The data to be returned in the response.
    :param message: A message describing the response.
    :param status: The status of the response (e.g., "success", "error").
    :param code: The HTTP status code for the response.
    :return: A Response object with standardized structure.
    """
    return Response(
        {
            "status": status,
            "message": message,
            "data": data
        },
        status=status_code
    )

def custom_error_response(message="Error", status="error", status_code=400):
    """
    Custom error response function to standardize API error responses.

    :param message: A message describing the error.
    :param status: The status of the response (e.g., "success", "error").
    :param status_code: The HTTP status code for the response.
    :return: A Response object with standardized structure for errors.
    """
    return Response(
        {
            "status": status,
            "message": message,
            "data": None
        },
        status=status_code
    )

def paginated_custom_response(paginator, page, data, message="Data retrieved successfully", status_code=200):
    """
    Standard paginated response.
    """
    return custom_response(
        data={
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": data
        },
        message=message,
        status_code=status_code
    )