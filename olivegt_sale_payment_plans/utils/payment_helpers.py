from dateutil.relativedelta import relativedelta


def calculate_installment_dates(start_date, count, frequency):
    """
    Calculate installment dates based on start date, count, and frequency.
    
    Args:
        start_date (date): Starting date for installments
        count (int): Number of installments
        frequency (str): 'month', 'week', or 'day'
        
    Returns:
        list: List of dates for each installment
    """
    result = []
    current_date = start_date
    
    for i in range(count):
        result.append(current_date)
        if frequency == 'month':
            current_date = current_date + relativedelta(months=1)
        elif frequency == 'week':
            current_date = current_date + relativedelta(weeks=1)
        else:  # day
            current_date = current_date + relativedelta(days=1)
    
    return result


def calculate_equal_installments(total_amount, count, initial_amount=0, final_amount=0):
    """
    Calculate equal installment amounts.
    
    Args:
        total_amount (float): Total amount to distribute
        count (int): Number of installments
        initial_amount (float): Initial payment amount
        final_amount (float): Final payment amount
        
    Returns:
        float: Amount per installment
    """
    remaining = total_amount - initial_amount - final_amount
    if remaining < 0:
        return 0
    
    if count <= 0:
        return 0
        
    return remaining / count
