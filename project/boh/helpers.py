def data_sensitivity_value(data_elements):
    """Calculates the data sensitivity value."""
    from .models import DataElement
    vector = {
        DataElement.GLOBAL_CATEGORY: 1.0,
        DataElement.PERSONAL_CATEGORY: 0.0,
        DataElement.GOVERNMENT_CATEGORY: 0.0,
        DataElement.PCI_CATEGORY: 0.0,
        DataElement.MEDICAL_CATEGORY: 0.0,
        DataElement.COMPANY_CATEGORY: 0.0,
    }

    for data_element in data_elements:
        vector[data_element.category] += data_element.weight

    # DSV = Global * (Personal + Government) + PCI + Medical + Company
    dsv = (
        vector[DataElement.GLOBAL_CATEGORY] *
        (
            vector[DataElement.PERSONAL_CATEGORY] +
            vector[DataElement.GOVERNMENT_CATEGORY]
        ) +
        vector[DataElement.PCI_CATEGORY] +
        vector[DataElement.MEDICAL_CATEGORY] +
        vector[DataElement.COMPANY_CATEGORY]
    )

    return dsv


def data_classification_level(dsv):
    """Returns the data classification level of the calculated data sensitivity value."""
    if dsv < 5:
        return 0
    if dsv < 15:
        return 1
    elif 15 <= dsv < 100:
        return 2
    elif 100 <= dsv < 150:
        return 3
    else:
        return 4


def data_classification_level_display(dcl):
    """Returns the data classification level of the calculated data sensitivity value."""
    if dcl == 0:
        return "Public"
    if dcl == 1:
        return "Private"
    elif dcl == 2:
        return "Confidential"
    elif dcl == 3:
        return "Sensitive"
    elif dcl == 4:
        return "Highly Sensitive"
    else:
        return "None"
