import pytest
from sentinel_host.network_share import board_url, NetworkShareDialog

@pytest.mark.parametrize('address', ['example.com', '192.168.2.99/evil', '0.0.0.0', '224.0.0.1', '255.255.255.255'])
def test_qr_rejects_non_device_addresses(address):
    with pytest.raises(ValueError):
        board_url(address)

def test_dialog_has_board_lan_url_without_starting_service():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = NetworkShareDialog('192.168.2.99')
    assert dialog.url == 'http://192.168.2.99:8080/'
    assert dialog.address_label.text() == dialog.url
    dialog.close()
