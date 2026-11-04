#!/usr/bin/env python3
"""Compare natural payload coordinates, without building/adopting a container."""
from capture_a0_formats import align, require


def payload_geometry(inventory, replacements):
    sequences={'boot_v3':('kernel','ramdisk'),'vendor_boot_v3':('ramdisk','dtb')}
    require(inventory['kind'] in sequences,'only observed v3 payload coordinates')
    sequence=sequences[inventory['kind']]; rows={r['name']:r for r in inventory['parts']}
    page=inventory['page_size']; require(page == 4096,'requires observed page size')
    require(set(replacements) <= set(sequence),'unknown payload size')
    cursor=align(rows['header']['end'],page); payloads=[]
    for name in sequence:
        size=replacements.get(name,rows[name]['bytes'])
        require(type(size) is int and 0 < size <= 128*1024*1024,'payload size bound/type')
        payloads.append(dict(name=name,stock_start=rows[name]['start'],start=cursor,bytes=size,
            coordinate_delta=cursor-rows[name]['start'],size_delta=size-rows[name]['bytes']))
        cursor=align(cursor+size,page)
    return dict(payloads=payloads,natural_body_end=cursor,stock_body_end=inventory['body_end'],
        body_end_delta=cursor-inventory['body_end'],stock_file_bytes=inventory['bytes'],
        payload_body_within_stock_file=cursor <= inventory['bytes'],
        physical_partition_capacity_established=False,
        opaque_signature_and_vbmeta_placement_defined=False,container_built=False)


def package_options(stock, measured):
    image=measured['image']['comparison']; profiles=measured['profiles']
    stock_kernel=image['stock_bytes']; stock_gzip=measured['stock_vendor_ramdisk']['gzip_bytes']
    length=image['candidate_bytes']; stripped=profiles['strip_debug']['gzip_bytes']
    full=profiles['as_built']['gzip_bytes']
    boot=payload_geometry(stock['boot.img']['inventory'],{'kernel':length})
    require(stock_kernel == next(r['bytes'] for r in stock['boot.img']['inventory']['parts'] if r['name']=='kernel'),
        'kernel references differ')
    require(stock_gzip == next(r['bytes'] for r in stock['vendor_boot.img']['inventory']['parts'] if r['name']=='ramdisk'),
        'ramdisk references differ')
    return dict(
        fixed_geometry=dict(kernel_filler_bytes=stock_kernel-length,strip_gzip_filler_bytes=stock_gzip-stripped,
            current_packer_accepts_natural_payloads=length == stock_kernel and stripped == stock_gzip,
            image_padding_semantics_validated=False,gzip_padding_semantics_validated=False),
        natural_lengths_strip_debug=dict(boot=boot,
            vendor_boot=payload_geometry(stock['vendor_boot.img']['inventory'],{'ramdisk':stripped}),
            current_packer_supports_geometry=False),
        natural_lengths_as_built=dict(boot=boot,
            vendor_boot=payload_geometry(stock['vendor_boot.img']['inventory'],{'ramdisk':full}),
            current_packer_supports_geometry=False),
        user_choice=None,strip_policy_adopted=False,padding_applied=False,geometry_adopted=False)


def validate_consumption(current, previous):
    require(current['selected_copy_readbacks_verified'] == 275
        and current['consumption']['native_inputs_verified'] == 275
        and current['consumption']['snapshots_sealed_during_extraction'] is True
        and current['consumption']['working_copy_paths_reconsumed'] is False
        and all(current['consumption'][n] is True for n in (
            'archive_source_and_stock_same_checked_buffers','native_objcopy_and_strip_inputs_sealed',
            'ramdisk_replacements_checked_before_emit','gzip_replay_same_checked_buffer')), 'consumption proof incomplete')
    require(current['image']['sha256'] == previous['image']['sha256']
        and current['image']['comparison'] == previous['image']['comparison']
        and current['modules'] == previous['modules'], 'Image/module measurement changed')
    for mode in ('as_built','strip_debug'):
        for name in ('gzip_bytes','gzip_sha256','cpio_bytes','cpio_sha256'):
            require(current['profiles'][mode][name] == previous['profiles'][mode][name], 'ramdisk measurement changed')
    return dict(native_inputs_sealed=275,copy_readbacks_verified=275,
        module_measurements_equal_to_PR86=len(current['modules']),image_and_ramdisk_hashes_equal_to_PR86=True,
        all_pipeline_consumers_certified=False)
